"""
법령 개정 리스크 + 컨설팅 인사이트 전체 파이프라인

사용:
    from RISK.consulting import run_full_analysis, get_consulting_for_latest

    # 특정 버전 분석
    result = run_full_analysis("국세기본법", "LAW", "20250101_0001234")

    # 최신 버전 자동 선택
    result = get_consulting_for_latest("법인세법", "LAW")
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from RISK.chain import (
    RevisionObservationChain,
    AddendaObservationChain,
    AnnexObservationChain,
    ConsultingInsightChain,
    CrossLawImpactChain,
)
from RISK.models import (
    ConsultingInsightOutput,
    RevisionObservationOutput,
    CrossLawImpactOutput,
)
from RISK.run import (
    make_version_context,
    load_risk_cache,
    save_risk_cache,
    run_all_revision,
    run_all_addenda,
    run_all_annex_observation,
    AddendaMergedOutput,
    AnnexMergedOutput,
)

ROOT = Path(__file__).parent.parent
LAW_DIR = ROOT / "law"

LAW_SLUGS: dict[str, str] = {
    # 핵심 세법 8개
    "국세기본법": "gukse_basic",
    "국세징수법": "gukse_collection",
    "법인세법": "corporate_tax",
    "소득세법": "income_tax",
    "부가가치세법": "vat",
    "조세범처벌법": "tax_crime",
    "조세범처벌절차법": "tax_crime_proc",
    "국제조세조정에 관한 법률": "itcl",
    # 외부 참조 법령 6개 (세법과 연동)
    "조세특례제한법": "joseteukrejehan",
    "상속세 및 증여세법": "inheritance_tax",
    "관세법": "customs",
    "종합부동산세법": "comprehensive_realty",
    "개별소비세법": "individual_consumption",
    "자본시장과 금융투자업에 관한 법률": "capital_market",
}

# 세법과 연동 관계 (외부 법령 → 영향받는 핵심 세법)
CROSS_LAW_LINKS: dict[str, list[str]] = {
    "조세특례제한법": ["법인세법", "소득세법", "부가가치세법", "국세기본법"],
    "상속세 및 증여세법": ["국세기본법", "소득세법"],
    "관세법": ["부가가치세법", "국세기본법"],
    "종합부동산세법": ["국세기본법", "소득세법"],
    "개별소비세법": ["부가가치세법", "국세기본법"],
    "자본시장과 금융투자업에 관한 법률": ["소득세법", "법인세법"],
}

KIND_FOLDER: dict[str, str] = {
    "LAW": "law",
    "DECREE": "decree",
    "RULE": "rule",
}


# ── DRF JSON → converted 변환 ──────────────────────────────────────────────

SOURCE_TYPE_MAP: dict[str, str] = {
    "LAW": "law",
    "DECREE": "admrul",
    "RULE": "admrule",
}


def _flatten_nested(obj, sep: str = "\n") -> str:
    """중첩 리스트/문자열을 하나의 텍스트로 평탄화."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        parts = []
        for item in obj:
            parts.append(_flatten_nested(item, sep))
        return sep.join(p for p in parts if p)
    return str(obj)


def drf_json_to_converted(drf_json: dict, kind: str) -> dict:
    """
    법제처 DRF 원본 JSON → RISK 파이프라인이 기대하는 converted 형식으로 변환.

    Parameters
    ----------
    drf_json : DRF lawService.do?type=JSON 응답 ({"법령": {...}})
    kind     : "LAW" | "DECREE" | "RULE"
    """
    law_data = drf_json.get("법령", drf_json)  # 최상위에 "법령" 키가 없을 수도 있음
    basic = law_data.get("기본정보", {})

    law_name = basic.get("법령명_한글", "")
    promulgated_at = str(basic.get("공포일자", ""))
    promulgation_no = str(basic.get("공포번호", ""))
    effective_at = str(basic.get("시행일자", ""))

    # 제개정이유 + 개정문
    ri_raw = law_data.get("제개정이유", {})
    ri_content = ri_raw.get("제개정이유내용", "") if isinstance(ri_raw, dict) else ri_raw
    revision_reason_text = _flatten_nested(ri_content)

    gm_raw = law_data.get("개정문", {})
    gm_content = gm_raw.get("개정문내용", "") if isinstance(gm_raw, dict) else gm_raw
    amendment_text = _flatten_nested(gm_content)

    # 부칙 — 이번 개정 버전의 공포번호와 일치하는 것만 추출
    buchik_raw = law_data.get("부칙", {})
    buchik_units = buchik_raw.get("부칙단위", []) if isinstance(buchik_raw, dict) else []
    if isinstance(buchik_units, dict):
        buchik_units = [buchik_units]

    addenda = []
    for unit in buchik_units:
        if not isinstance(unit, dict):
            continue
        unit_pno = str(unit.get("부칙공포번호", "")).lstrip("0")
        cur_pno = promulgation_no.lstrip("0")
        # 이번 개정 버전의 부칙만 포함 (부칙이 여러 버전 누적된 경우 대비)
        if cur_pno and unit_pno and unit_pno != cur_pno:
            continue
        date = str(unit.get("부칙공포일자", "")).replace(".", "")
        text_raw = unit.get("부칙내용", "")
        text = _flatten_nested(text_raw)
        if date and text:
            addenda.append({"date": date, "text": text})

    # 별표 (있는 경우)
    annexes = []
    byeolpyo_raw = law_data.get("별표", {})
    if isinstance(byeolpyo_raw, dict):
        byeolpyo_units = byeolpyo_raw.get("별표단위", [])
        if isinstance(byeolpyo_units, dict):
            byeolpyo_units = [byeolpyo_units]
        for i, unit in enumerate(byeolpyo_units):
            if not isinstance(unit, dict):
                continue
            annexes.append({
                "id": unit.get("별표키", f"ANNEX_{i:04d}"),
                "title": _flatten_nested(unit.get("별표제목", "")),
                "content": [_flatten_nested(unit.get("별표내용", ""))],
            })

    return {
        "law_name": law_name,
        "source_type": SOURCE_TYPE_MAP.get(kind, "law"),
        "metadata": {
            "공포일자": promulgated_at,
            "공포번호": promulgation_no,
            "시행일자": effective_at,
        },
        "revision_reasons": [revision_reason_text] if revision_reason_text else [],
        "amendments": [amendment_text] if amendment_text else [],
        "addenda": addenda,
        "annexes": annexes,
    }


# ── 법령 데이터 로더 ────────────────────────────────────────────────────────

def _version_index_path(law_name: str, kind: str) -> Path:
    slug = LAW_SLUGS.get(law_name)
    if not slug:
        raise ValueError(f"지원하지 않는 법령: {law_name}")
    folder = KIND_FOLDER.get(kind)
    if not folder:
        raise ValueError(f"지원하지 않는 kind: {kind}")
    return LAW_DIR / slug / folder / "_version_index.json"


def get_latest_version_key(law_name: str, kind: str) -> str:
    """_version_index.json에서 최신 공포일자 기준 version_key 반환."""
    idx_path = _version_index_path(law_name, kind)
    if not idx_path.exists():
        raise FileNotFoundError(f"버전 인덱스 없음: {idx_path}")

    with idx_path.open(encoding="utf-8") as f:
        index: dict = json.load(f)

    # index: { pno_stripped -> {version_key, pdate, pno, ...} }
    latest = max(index.values(), key=lambda v: v["version_key"])
    return latest["version_key"]


def list_version_keys(law_name: str, kind: str) -> list[str]:
    """최신순 정렬된 version_key 목록."""
    idx_path = _version_index_path(law_name, kind)
    if not idx_path.exists():
        return []
    with idx_path.open(encoding="utf-8") as f:
        index: dict = json.load(f)
    return sorted([v["version_key"] for v in index.values()], reverse=True)


def load_law_json(law_name: str, kind: str, version_key: str) -> dict:
    """version_key('YYYYMMDD_PPPPPPP') 기준 법령 JSON 로드."""
    idx_path = _version_index_path(law_name, kind)
    with idx_path.open(encoding="utf-8") as f:
        index: dict = json.load(f)

    entry = next(
        (v for v in index.values() if v["version_key"] == version_key),
        None,
    )
    if not entry:
        raise KeyError(f"{law_name}/{kind}: version_key '{version_key}' 없음")

    slug = LAW_SLUGS[law_name]
    folder = KIND_FOLDER[kind]
    json_file = LAW_DIR / slug / folder / entry["file"]

    if not json_file.exists():
        raise FileNotFoundError(f"법령 JSON 파일 없음: {json_file}")

    with json_file.open(encoding="utf-8") as f:
        return json.load(f)


# ── 컨설팅 인사이트 캐시 ────────────────────────────────────────────────────

def _consulting_cache_path(ctx: dict) -> str:
    return os.path.join(ctx["base_dir"], "risk", "consulting.json")


def _load_consulting_cache(ctx: dict) -> Optional[ConsultingInsightOutput]:
    path = _consulting_cache_path(ctx)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return ConsultingInsightOutput(**json.load(f))


def _save_consulting_cache(ctx: dict, out: ConsultingInsightOutput) -> None:
    path = _consulting_cache_path(ctx)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out.model_dump(), f, ensure_ascii=False, indent=2)


# ── 컨설팅 인사이트 실행 ────────────────────────────────────────────────────

def _build_addenda_summary(addenda_merged: Optional[AddendaMergedOutput]) -> str:
    if not addenda_merged or not addenda_merged.addenda:
        return "부칙 없음"
    parts = []
    for ada in addenda_merged.addenda:
        roles = ", ".join(r.role for r in (ada.roles or []))
        parts.append(f"[{ada.addenda_date}] {ada.summary or ''} | 역할: {roles}")
    return "\n".join(parts)


def run_consulting_insight(
    converted: dict,
    rev_out: RevisionObservationOutput,
    addenda_merged: Optional[AddendaMergedOutput],
    annex_merged: Optional[AnnexMergedOutput],
    chain: ConsultingInsightChain,
) -> ConsultingInsightOutput:
    ctx = make_version_context(converted)

    cached = _load_consulting_cache(ctx)
    if cached:
        return cached

    observed_changes_json = json.dumps(
        [c.model_dump() for c in (rev_out.observed_changes or [])],
        ensure_ascii=False, indent=2,
    )

    addenda_summary = _build_addenda_summary(addenda_merged)

    risk_signals: list = []
    # AnnexMergedOutput에는 risk_signals이 없으므로 rev_out에서만 가져옴
    # (IntegratedRevisionFeatureOutput의 risk_signals은 별도 체인 — 여기서는 건너뜀)
    risk_signals_json = json.dumps(risk_signals, ensure_ascii=False, indent=2)

    out = chain.analyze(
        law_name=rev_out.law_name,
        law_type=rev_out.law_type,
        promulgated_at=rev_out.promulgated_at,
        effective_at=rev_out.effective_at or "미지정",
        observed_changes_json=observed_changes_json,
        addenda_summary=addenda_summary,
        risk_signals_json=risk_signals_json,
    )

    # 메타 고정
    out.law_name = rev_out.law_name
    out.law_type = rev_out.law_type
    out.promulgated_at = rev_out.promulgated_at
    out.effective_at = rev_out.effective_at or "미지정"

    _save_consulting_cache(ctx, out)
    return out


# ── 전체 파이프라인 ──────────────────────────────────────────────────────────

class FullAnalysisResult:
    def __init__(
        self,
        law_name: str,
        kind: str,
        version_key: str,
        revision: RevisionObservationOutput,
        addenda: Optional[AddendaMergedOutput],
        annexes: Optional[AnnexMergedOutput],
        consulting: ConsultingInsightOutput,
    ):
        self.law_name = law_name
        self.kind = kind
        self.version_key = version_key
        self.revision = revision
        self.addenda = addenda
        self.annexes = annexes
        self.consulting = consulting

    def to_dict(self) -> dict:
        return {
            "law_name": self.law_name,
            "kind": self.kind,
            "version_key": self.version_key,
            "revision": self.revision.model_dump(),
            "addenda": self.addenda.model_dump() if self.addenda else None,
            "annexes": self.annexes.model_dump() if self.annexes else None,
            "consulting": self.consulting.model_dump(),
        }


def run_full_analysis(
    law_name: str,
    kind: str,
    version_key: Optional[str] = None,
) -> FullAnalysisResult:
    """
    법령 1개 버전에 대해 Observation 3종 + 컨설팅 인사이트를 실행합니다.

    Parameters
    ----------
    law_name  : 법령 한글명 (LAW_SLUGS 키 중 하나)
    kind      : "LAW" | "DECREE" | "RULE"
    version_key : "YYYYMMDD_PPPPPPP" 형식. None이면 최신 버전 자동 선택.
    """
    if version_key is None:
        version_key = get_latest_version_key(law_name, kind)

    drf_json = load_law_json(law_name, kind, version_key)
    converted = drf_json_to_converted(drf_json, kind)

    rev_chain = RevisionObservationChain()
    add_chain = AddendaObservationChain()
    anx_chain = AnnexObservationChain()
    con_chain = ConsultingInsightChain()

    print(f"[1/4] Revision 관측 — {law_name} {kind} {version_key}")
    rev_out = run_all_revision(converted, rev_chain)

    print(f"[2/4] Addenda 관측")
    addenda_merged = run_all_addenda(converted, add_chain)

    print(f"[3/4] Annex 관측")
    annex_merged = run_all_annex_observation(converted, anx_chain)

    print(f"[4/4] 컨설팅 인사이트 도출")
    consulting = run_consulting_insight(
        converted, rev_out, addenda_merged, annex_merged, con_chain
    )

    print(f"✅ 완료 — overall_priority={consulting.overall_priority}")
    return FullAnalysisResult(
        law_name=law_name,
        kind=kind,
        version_key=version_key,
        revision=rev_out,
        addenda=addenda_merged,
        annexes=annex_merged,
        consulting=consulting,
    )


def get_consulting_for_latest(law_name: str, kind: str) -> ConsultingInsightOutput:
    """최신 버전 컨설팅 인사이트만 빠르게 반환."""
    result = run_full_analysis(law_name, kind)
    return result.consulting


# ── Cross-law 분석 ───────────────────────────────────────────────────────────

def _search_related_articles(query: str, n: int = 6) -> str:
    """벡터 DB에서 연동 세법 조문 검색."""
    try:
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        import os as _os

        ef = OpenAIEmbeddingFunction(
            api_key=_os.environ.get("OPENAI_API_KEY", ""),
            model_name="text-embedding-3-small",
        )
        client = chromadb.PersistentClient(path=str(ROOT / "vector_db" / "chroma"))
        col = client.get_collection("law_articles", embedding_function=ef)
        results = col.query(query_texts=[query], n_results=n)

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        lines = []
        for doc, meta in zip(docs, metas):
            law = meta.get("law_name", "")
            scope = meta.get("scope", "")
            art_id = meta.get("article_id", "")
            title = meta.get("title", "")
            lines.append(f"[{law} {scope} {art_id} {title}]\n{doc[:300]}")
        return "\n\n".join(lines)
    except Exception:
        return "(벡터 검색 불가)"


def _cross_law_cache_path(ctx: dict) -> str:
    return os.path.join(ctx["base_dir"], "risk", "cross_law.json")


def run_cross_law_analysis(
    law_name: str,
    kind: str = "LAW",
    version_key: Optional[str] = None,
) -> Optional[CrossLawImpactOutput]:
    """
    외부 참조 법령 개정 → 연동 세법 영향 분석.

    law_name이 CROSS_LAW_LINKS에 없는 핵심 세법이면 None 반환.
    """
    linked_laws = CROSS_LAW_LINKS.get(law_name)
    if not linked_laws:
        return None  # 핵심 세법은 cross-law 분석 대상 아님

    if version_key is None:
        version_key = get_latest_version_key(law_name, kind)

    drf_json = load_law_json(law_name, kind, version_key)
    converted = drf_json_to_converted(drf_json, kind)
    ctx = make_version_context(converted)

    # 캐시 확인
    cache_path = _cross_law_cache_path(ctx)
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return CrossLawImpactOutput(**json.load(f))

    # Observation (캐시 재활용)
    rev_chain = RevisionObservationChain()
    add_chain = AddendaObservationChain()
    rev_out = run_all_revision(converted, rev_chain)
    addenda_merged = run_all_addenda(converted, add_chain)

    observed_changes_json = json.dumps(
        [c.model_dump() for c in (rev_out.observed_changes or [])],
        ensure_ascii=False, indent=2,
    )
    addenda_summary = _build_addenda_summary(addenda_merged)
    linked_tax_laws = ", ".join(linked_laws)

    # 연동 조문 벡터 검색
    query = f"{law_name} 개정 관련 세법 조문"
    related_articles = _search_related_articles(query, n=8)

    chain = CrossLawImpactChain()
    out = chain.analyze(
        source_law=law_name,
        promulgated_at=rev_out.promulgated_at,
        effective_at=rev_out.effective_at or "미지정",
        observed_changes_json=observed_changes_json,
        addenda_summary=addenda_summary,
        linked_tax_laws=linked_tax_laws,
        related_articles=related_articles,
    )
    out.source_law = law_name
    out.source_version_key = version_key

    # 캐시 저장
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(out.model_dump(), f, ensure_ascii=False, indent=2)

    return out
