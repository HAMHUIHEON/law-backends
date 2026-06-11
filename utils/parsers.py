"""
CleanJsonParser — PydanticOutputParser에 전처리 추가.

LangChain chain에서 invoke()는 parse()를 우회하고 parse_result()를 직접 호출하므로
parse_result()를 오버라이드한다.

처리 케이스:
  1. [ // 주석 없음 ]           → // 줄 주석, /* */ 블록 주석 제거
  2. "설명 텍스트...\n{ ... }"  → 첫 { 또는 [ 부터 추출
  3. ```json ... ```            → 마크다운 코드 블록 추출
  4. 배열/객체 필드 내 빈 dict {} 제거 (LLM이 trailing {} 추가하는 경우 방어)
"""
from __future__ import annotations
import json
import re
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.outputs import Generation


def _strip_empty_dicts(obj):
    """재귀적으로 list 내 빈 dict {} 를 제거한다."""
    if isinstance(obj, list):
        return [_strip_empty_dicts(item) for item in obj if item != {}]
    if isinstance(obj, dict):
        return {k: _strip_empty_dicts(v) for k, v in obj.items()}
    return obj


class CleanJsonParser(PydanticOutputParser):

    def _parse_obj(self, obj):
        """
        LLM 출력 형태 불일치 방어:
        1. RootModel[List[X]]인데 {"root": [...]} dict로 오면 list 추출
        2. 일반 BaseModel인데 raw list로 오면 list 필드로 래핑
        """
        import pydantic
        # 1) RootModel + {"root": [...]} 또는 {"items": [...]} 형태 언랩
        if isinstance(obj, dict):
            try:
                if issubclass(self.pydantic_object, pydantic.RootModel):
                    # "root", "items", 단일 list 키 순서로 탐색
                    for key in ("root", "items", "citations", "records"):
                        if key in obj and isinstance(obj[key], list):
                            obj = [item for item in obj[key] if item != {}]
                            break
                    else:
                        # 단일 키이고 값이 list면 언랩
                        if len(obj) == 1:
                            val = next(iter(obj.values()))
                            if isinstance(val, list):
                                obj = [item for item in val if item != {}]
            except TypeError:
                pass

        # 2) raw list가 일반 BaseModel로 오면 list 필드로 래핑
        if isinstance(obj, list):
            obj = [item for item in obj if item != {}]
            try:
                if not issubclass(self.pydantic_object, pydantic.RootModel):
                    fields = self.pydantic_object.model_fields
                    list_field = next(
                        (k for k, f in fields.items()
                         if "List" in str(f.annotation)),
                        None
                    )
                    if list_field:
                        obj = {list_field: obj}
            except TypeError:
                pass

        return super()._parse_obj(obj)

    def parse_result(self, result, *, partial: bool = False):
        # ChatGeneration.text는 message.content의 property이므로 .text로 통일
        text = result[0].text if result else ""

        # 1) // 줄 주석 제거
        cleaned = re.sub(r"//[^\n]*", "", text)
        # 2) /* */ 블록 주석 제거
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)

        # 3) 마크다운 코드 블록 우선 추출
        md_match = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
        if md_match:
            cleaned = md_match.group(1).strip()
        else:
            # 4) 앞에 자연어 설명이 있으면 첫 { 또는 [ 부터 추출
            bracket = re.search(r"[{\[]", cleaned)
            if bracket:
                cleaned = cleaned[bracket.start():]

        # 5) 빈 dict 제거 (LLM이 trailing {} 를 끼워넣는 경우 방어)
        try:
            parsed = json.loads(cleaned)
            cleaned = json.dumps(_strip_empty_dicts(parsed), ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass  # JSON 파싱 불가면 그대로 넘김

        return super().parse_result([Generation(text=cleaned)], partial=partial)
