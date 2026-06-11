"""
LLM 마이그레이션 v2: ChatOpenAI → utils.llm.get_llm / DEFAULT_MODEL (claude-sonnet-4-6)

처리 순서:
  1. from langchain_openai import ChatOpenAI → from utils.llm import get_llm
  2. from langchain.chat_models import ChatOpenAI → from utils.llm import get_llm
  3. ChatOpenAI( → get_llm(
  4. "gpt-4.1" / "gpt-5.1" 문자열 → DEFAULT_MODEL
  5. DEFAULT_MODEL / _MODEL / MODEL 상수 대입 → import로 교체
  6. from utils.llm import get_llm (단독) → from utils.llm import get_llm, DEFAULT_MODEL (DEFAULT_MODEL 사용 시)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
EXCLUDE = {"scripts", "chroma_db", "vector_db", "cache", "law", "cases", ".venv", "logs"}

GPT_RE  = re.compile(r'"gpt-[45]\.1"')
CONST_RE = re.compile(r'^(?:DEFAULT_MODEL|_MODEL|MODEL)\s*=\s*"gpt-[45]\.1".*$', re.MULTILINE)
IMPORT_OAI_RE  = re.compile(r'from langchain_openai import ChatOpenAI\r?\n')
IMPORT_OLD_RE  = re.compile(r'from langchain\.chat_models import ChatOpenAI\r?\n')
CHAT_RE = re.compile(r'\bChatOpenAI\(')

# utils.llm import 라인들
IMPORT_GET_LLM   = re.compile(r'from utils\.llm import get_llm(?:,\s*DEFAULT_MODEL)?\s*\r?\n')
IMPORT_DM_ONLY   = re.compile(r'from utils\.llm import DEFAULT_MODEL.*\r?\n')


def migrate(text: str) -> str:
    # 1. import 교체
    text = IMPORT_OAI_RE.sub("from utils.llm import get_llm\n", text)
    text = IMPORT_OLD_RE.sub("from utils.llm import get_llm\n", text)

    # 2. ChatOpenAI( → get_llm(
    text = CHAT_RE.sub("get_llm(", text)

    # 3. "gpt-4.1" / "gpt-5.1" → DEFAULT_MODEL
    text = GPT_RE.sub("DEFAULT_MODEL", text)

    # 4. 상수 대입 행 제거 (이제 불필요, import로 대체)
    #    DEFAULT_MODEL = DEFAULT_MODEL → 삭제
    text = re.sub(
        r'^(?:DEFAULT_MODEL|_MODEL|MODEL)\s*=\s*DEFAULT_MODEL.*\n',
        "",
        text,
        flags=re.MULTILINE,
    )

    # 5. get_llm import를 get_llm + DEFAULT_MODEL import로 업그레이드 (DEFAULT_MODEL 사용 시)
    uses_dm = "DEFAULT_MODEL" in text
    has_get_llm_import = bool(IMPORT_GET_LLM.search(text))
    has_dm_import      = bool(IMPORT_DM_ONLY.search(text))

    if uses_dm and has_get_llm_import and not has_dm_import:
        # get_llm 단독 import → get_llm, DEFAULT_MODEL
        text = IMPORT_GET_LLM.sub(
            "from utils.llm import get_llm, DEFAULT_MODEL\n",
            text,
            count=1,
        )
    elif uses_dm and not has_get_llm_import and not has_dm_import:
        # import가 아예 없으면 파일 맨 위에 추가 (import 블록 뒤)
        text = "from utils.llm import DEFAULT_MODEL\n" + text

    # 6. 중복 import 정리
    #    get_llm, DEFAULT_MODEL 중복 라인 제거
    text = re.sub(
        r'(from utils\.llm import get_llm, DEFAULT_MODEL\n)'
        r'(from utils\.llm import (?:get_llm|DEFAULT_MODEL)[^\n]*\n)',
        r'\1',
        text,
    )

    return text


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE:
        return True
    if path.name == Path(__file__).name:
        return True
    if path.name == "llm.py" and "utils" in path.parts:
        return True
    return False


def run() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    py_files = [p for p in ROOT.rglob("*.py") if not should_skip(p)]

    changed: list[Path] = []
    for f in sorted(py_files):
        try:
            original = f.read_text(encoding="utf-8")
        except Exception:
            continue
        new = migrate(original)
        if new != original:
            f.write_text(new, encoding="utf-8")
            changed.append(f)
            print(f"  ✅ {f.relative_to(ROOT)}")

    print(f"\n총 {len(changed)}/{len(py_files)}개 파일 수정")


if __name__ == "__main__":
    run()
