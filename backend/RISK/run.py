from pathlib import Path
from typing import Union, List, Literal,TypedDict,Optional
from pydantic import BaseModel
import re
import json
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from RISK.models import (RevisionObservationInput,RevisionObservationOutput,
                         AddendaObservationInput,AddendaObservationOutput,
                         AnnexObservationOutput,AnnexObservationInput)
from RISK.chain import (RevisionObservationChain,AddendaObservationChain,AnnexObservationChain)
import os


"""
cache/
  {law_name}/
    {공포일자}_{공포번호}/
      risk/
        revision.json
        addenda/
        annex/
        annex_merged.json

"""
#캐쉬함수
class VersionContext(TypedDict):
    law_name: str
    promulgated_at: str
    promulgation_no: str
    base_dir: str

def make_version_context(law: dict) -> VersionContext:
    law_name = law["law_name"]
    meta = law["metadata"]

    promulgated_at = meta["공포일자"]
    promulgation_no = meta["공포번호"]

    ver_key = f"{promulgated_at}_{promulgation_no}"
    base_dir = f"cache/{law_name}/{ver_key}"

    os.makedirs(base_dir, exist_ok=True)

    return {
        "law_name": law_name,
        "promulgated_at": promulgated_at,
        "promulgation_no": promulgation_no,
        "base_dir": base_dir,
    }



def risk_cache_path(ctx: dict, *paths) -> str:
    """
    ctx: make_version_context에서 생성한 컨텍스트
    paths: ("risk", "annex", "ANNEX_0000_1.json") 등
    """
    base = os.path.join(ctx["base_dir"], "risk")
    path = os.path.join(base, *paths)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def load_risk_cache(ctx: dict, *paths) -> Optional[dict]:
    path = risk_cache_path(ctx, *paths)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_risk_cache(ctx: dict, obj, *paths) -> str:
    path = risk_cache_path(ctx, *paths)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


#헬퍼함수
def flatten_text_blocks(blocks) -> str:
    """
    blocks:
      - List[str]
      - List[dict]
      - List[mixed]
    목적:
      - 사람이 읽을 수 있는 텍스트만 안전하게 연결
    """
    texts = []

    for b in blocks or []:
        if isinstance(b, str):
            texts.append(b)
        elif isinstance(b, dict):
            # 가장 보수적인 선택: value 중 str만
            for v in b.values():
                if isinstance(v, str):
                    texts.append(v)
        else:
            texts.append(str(b))

    return "\n".join(texts).strip()




LAW_TYPE_MAP = {
    "law": "LAW",
    "admrul": "DECREE",
    "admrule": "RULE",
}

def extract_revision_observation_input(converted: dict) -> RevisionObservationInput:
    # 1) law_name
    law_name = converted["law_name"]

    # 2) law_type 정규화
    raw_type = converted["source_type"]
    law_type = LAW_TYPE_MAP.get(raw_type)
    if law_type is None:
        raise ValueError(f"Unknown law_type: {raw_type!r}")

    # 3) metadata 날짜 (원본 그대로: "YYYYMMDD")
    md = converted["metadata"]
    promulgated_at = md.get("공포일자")
    effective_at = md.get("시행일자")

    if not promulgated_at:
        raise ValueError("metadata.공포일자 is required")

    # 4) revision_reasons / amendments (각각 [text] 형태)
    # - 리스트면 join해서 하나의 텍스트로
    revision_reason = flatten_text_blocks(converted.get("revision_reasons", []))
    revision_text = flatten_text_blocks(converted.get("amendments", []))
    
    return RevisionObservationInput(
        law_name=law_name,
        law_type=law_type,
        promulgated_at=str(promulgated_at),
        effective_at=str(effective_at) if effective_at else None,
        revision_reason=revision_reason,
        revision_text=revision_text,
    )


def run_revision_observation(
    converted: dict,
    chain: RevisionObservationChain,
) -> RevisionObservationOutput:
    """
    Revision 관측 (version-aware cache)
    - cache key: law_name / 공포일자_공포번호
    - 결과는 항상 해당 버전에 종속
    """

    # 🔹 version context 생성
    ctx = make_version_context(converted)

    # 🔹 cache load 시도
    cached = load_risk_cache(ctx, "revision.json")
    if cached:
        return RevisionObservationOutput(**cached)

    # 1️⃣ input 생성
    inp = extract_revision_observation_input(converted)

    # 2️⃣ LLM 관측
    out = chain.observe(inp)

    # 3️⃣ 메타 고정 (LLM 추정 차단)
    out.law_name = inp.law_name
    out.law_type = inp.law_type
    out.promulgated_at = inp.promulgated_at
    out.effective_at = inp.effective_at

    # 4️⃣ cache save
    save_risk_cache(
        ctx,
        out.model_dump(),
        "revision.json"
    )

    return out

def run_all_revision(
    converted: dict,
    chain: RevisionObservationChain,
) -> RevisionObservationOutput:
    ctx = make_version_context(converted)

    # side-effect run
    run_revision_observation(converted, chain)

    # 최종 결과는 캐시에서만 로드
    cached = load_risk_cache(ctx, "revision.json")
    if not cached:
        raise RuntimeError("revision cache missing")

    return RevisionObservationOutput(**cached)


#부칙 
def get_mapped_law_type(converted: dict) -> str:
    """
    converted의 원천 타입 키는 'source_type'을 표준으로 사용.
    반환: "LAW" | "DECREE" | "RULE"
    """
    raw_type = converted.get("source_type")
    if raw_type is None:
        raise KeyError("converted['source_type'] is required")

    mapped = LAW_TYPE_MAP.get(raw_type)
    if mapped is None:
        raise ValueError(f"Unknown source_type: {raw_type!r}")

    return mapped

def extract_addenda_observation_input(
    converted: dict,
    addendum: dict
) -> AddendaObservationInput:
    """
    converted: 전체 converted JSON
    addendum: converted["addenda"]의 개별 요소
    """

    # 1) 법령 기본 정보
    law_name = converted["law_name"]
    law_type = get_mapped_law_type(converted)  # ✅ 여기로 통일

    # 2) addenda 필수 필드
    addenda_date = addendum.get("date")
    addenda_text = addendum.get("text")

    if not addenda_date:
        raise ValueError("addendum.date is required")
    if not addenda_text:
        raise ValueError("addendum.text is required")

    return AddendaObservationInput(
        law_name=law_name,
        law_type=law_type,
        addenda_date=str(addenda_date),   # YYYYMMDD 그대로
        addenda_text=str(addenda_text),
    )


"""
cache/
 └─ {law_name}/
     └─ {공포일자}_{공포번호}/
         └─ risk/
             ├─ addenda/
             │   ├─ 20240101.json
             │   ├─ 20240315.json
             │   └─ ...
             └─ addenda_merged.json

"""
class AddendaMergedOutput(BaseModel):
    law_name: str
    law_type: Literal["LAW", "DECREE", "RULE"]
    addenda: list[AddendaObservationOutput]


def merge_addenda_cache(
    ctx: dict,
) -> Optional[AddendaMergedOutput]:
    """
    version context 기준 부칙 merge
    """

    addenda_dir = os.path.join(ctx["base_dir"], "risk", "addenda")
    if not os.path.exists(addenda_dir):
        return None

    items: list[AddendaObservationOutput] = []

    for fname in os.listdir(addenda_dir):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(addenda_dir, fname), "r", encoding="utf-8") as f:
            items.append(AddendaObservationOutput(**json.load(f)))

    if not items:
        return None

    # 날짜 기준 정렬 (YYYYMMDD)
    items.sort(key=lambda x: x.addenda_date)

    merged = AddendaMergedOutput(
        law_name=ctx["law_name"],
        law_type=items[0].law_type,
        addenda=items,
    )

    save_risk_cache(
        ctx,
        merged.model_dump(),
        "addenda_merged.json"
    )

    return merged


def run_addenda_observation(
    converted: dict,
    chain: AddendaObservationChain,
) -> list[AddendaObservationOutput]:
    """
    Addenda 관측 (version-aware)
    - 개별 addenda는 날짜 단위 캐시
    - merge는 side-effect로만 수행
    """

    ctx = make_version_context(converted)
    results: list[AddendaObservationOutput] = []

    for addendum in converted.get("addenda", []):
        # 1️⃣ input 생성
        inp = extract_addenda_observation_input(converted, addendum)

        fname = f"{inp.addenda_date}.json"

        # 2️⃣ cache load
        cached = load_risk_cache(ctx, "addenda", fname)
        if cached:
            out = AddendaObservationOutput(**cached)
        else:
            # 3️⃣ LLM 관측
            out = chain.observe(inp)

            # 4️⃣ 메타 고정
            out.law_name = inp.law_name
            out.law_type = inp.law_type
            out.addenda_date = inp.addenda_date

            # 5️⃣ cache save
            save_risk_cache(
                ctx,
                out.model_dump(),
                "addenda",
                fname
            )

        results.append(out)

    # 🔹 여기서 "머지 실행만" 한다
    merge_addenda_cache(ctx)

    return results

def run_all_addenda(
    converted: dict,
    chain: AddendaObservationChain,
) -> Optional[AddendaMergedOutput]:
    """
    부칙 전체 파이프라인 (도메인 진입점)

    - side-effect run 실행
    - version ctx 기준 merged 결과만 반환
    """

    # 1️⃣ side-effect run (개별 관측 + 캐시 + merge)
    run_addenda_observation(converted, chain)

    # 2️⃣ 최종 결과는 캐시에서만 로드
    ctx = make_version_context(converted)
    merged = load_risk_cache(ctx, "addenda_merged.json")

    if not merged:
        return None

    return AddendaMergedOutput(**merged)


#별표 - 운영리스크
def chunk_text_by_chars(text: str, max_chars: int) -> list[str]:
    if not text:
        return []

    chunks = []
    start = 0
    n = len(text)

    while start < n:
        end = start + max_chars
        chunks.append(text[start:end])
        start = end

    return chunks

MAX_ANNEX_CHARS = 16000  # 유지

def extract_annexes(converted: dict) -> list[AnnexObservationInput]:
    annex_inputs: list[AnnexObservationInput] = []

    for annex in converted.get("annexes", []):
        # 🔹 원본 annex id (예: "ANNEX_0000")
        annex_base_id = str(annex.get("id")).strip()
        if not annex_base_id:
            continue  # id 없는 건 스킵 (안전)

        title = annex.get("title", "").strip()

        raw_content = flatten_text_blocks(
            annex.get("content_raw") or annex.get("content")
        )

        # 🔹 content chunk 분할
        chunks = chunk_text_by_chars(raw_content, MAX_ANNEX_CHARS)

        # 🔹 chunk가 1개면 suffix 없이 그대로
        if len(chunks) == 1:
            annex_inputs.append(
                AnnexObservationInput(
                    annex_id=annex_base_id,
                    title=title,
                    content=chunks[0],
                )
            )
            continue

        # 🔹 여러 chunk → ANNEX_0000_1, ANNEX_0000_2 ...
        for i, chunk in enumerate(chunks, start=1):
            annex_inputs.append(
                AnnexObservationInput(
                    annex_id=f"{annex_base_id}_{i}",
                    title=f"{title} (part {i})",
                    content=chunk,
                )
            )

    return annex_inputs


from collections import defaultdict

def split_annex_id(annex_id: str) -> tuple[str, int | None]:
    """
    ANNEX_0000_2 -> ("ANNEX_0000", 2)
    ANNEX_0000   -> ("ANNEX_0000", None)
    """
    s = str(annex_id).strip()
    if "_" not in s:
        return s, None
    base, _, tail = s.rpartition("_")
    try:
        return base, int(tail)
    except ValueError:
        return s, None


#chunk-> base annex merge 로직
def merge_annex_chunks(
    chunks: list[AnnexObservationOutput]
) -> AnnexObservationOutput:
    base = chunks[0]

    # role: 다수결
    roles = [c.role for c in chunks if c.role]
    role = max(set(roles), key=roles.count) if roles else base.role

    # description: 첫 non-empty
    description = next(
        (c.description for c in chunks if c.description),
        base.description
    )

    # related_articles: union
    article_map = {}
    for c in chunks:
        for ra in c.related_articles or []:
            article_map[ra.article_ref] = ra

    return AnnexObservationOutput(
        annex_id=split_annex_id(base.annex_id)[0],  # base id로 복원
        title=base.title,
        role=role,
        description=description,
        related_articles=list(article_map.values()),
    )


class AnnexMergedOutput(BaseModel):
    law_name: str
    law_type: Literal["LAW", "DECREE", "RULE"]
    annexes: List[AnnexObservationOutput]


def merge_annex_cache(
    ctx: dict,
) -> Optional[AnnexMergedOutput]:
    annex_dir = os.path.join(ctx["base_dir"], "risk", "annex")
    if not os.path.exists(annex_dir):
        return None

    items: list[AnnexObservationOutput] = []

    for fname in os.listdir(annex_dir):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(annex_dir, fname), "r", encoding="utf-8") as f:
            items.append(AnnexObservationOutput(**json.load(f)))

    if not items:
        return None

    # 🔹 base annex 기준 grouping
    groups: dict[str, list[AnnexObservationOutput]] = defaultdict(list)
    for item in items:
        base_id, _ = split_annex_id(item.annex_id)
        groups[base_id].append(item)

    merged_annexes: list[AnnexObservationOutput] = []

    for base_id in sorted(groups.keys()):
        merged_annexes.append(
            merge_annex_chunks(groups[base_id])
        )

    merged = AnnexMergedOutput(
        law_name=ctx["law_name"],
        law_type=merged_annexes[0].law_type if merged_annexes else None,
        annexes=merged_annexes,
    )

    save_risk_cache(
        ctx,
        merged.model_dump(),
        "annex_merged.json"
    )

    return merged



def run_annex_observation(
    converted: dict,
    chain: AnnexObservationChain,
) -> None:
    """
    ANNEX chunk 관측 엔진
    - chunk 단위 LLM 관측
    - version-aware cache 저장
    - 반환값 없음 (side-effect 전용)
    """

    ctx = make_version_context(converted)

    for annex in converted.get("annexes", []):
        base_id = annex.get("id")
        if not base_id:
            continue

        title = annex.get("title", "").strip()
        raw = flatten_text_blocks(
            annex.get("content_raw") or annex.get("content")
        )

        chunks = chunk_text_by_chars(raw, MAX_ANNEX_CHARS)
        if not chunks:
            continue

        for idx, chunk in enumerate(chunks, start=1):
            annex_id = base_id if len(chunks) == 1 else f"{base_id}_{idx}"
            fname = f"{annex_id}.json"

            cached = load_risk_cache(ctx, "annex", fname)
            if cached:
                continue

            inp = AnnexObservationInput(
                annex_id=annex_id,
                title=title,
                content=chunk,
            )

            out = chain.observe(inp)

            # 메타 고정
            out.annex_id = annex_id
            out.title = title

            save_risk_cache(
                ctx,
                out.model_dump(),
                "annex",
                fname
            )



#별표 풀 파이프라인
def run_all_annex_observation(
    converted: dict,
    chain: AnnexObservationChain,
) -> Optional[AnnexMergedOutput]:
    """
    법령 1건에 대해:
    1) annex chunk 단위 관측(run + cache)
    2) annex base 단위로 merge
    3) 최종 AnnexMergedOutput 반환

    ⚠️ 이 함수의 반환값만이 '도메인에서 사용해야 할 결과'다.
    """

    # 1️⃣ chunk 단위 관측 + 캐시 적재
    run_annex_observation(
        converted=converted,
        chain=chain,
    )

    # 2️⃣ merge 결과 반환
    ctx = make_version_context(converted)
    merged = load_risk_cache(ctx, "annex_merged.json")

    if not merged:
            return None

    return AnnexMergedOutput(**merged)