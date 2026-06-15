# agents/court_agent.py — 법원 PDF 판례 에이전트 (pdf_court_cases Chroma 컬렉션)
import json
import os
from pathlib import Path
from typing import Optional

from langchain.tools import tool
from langchain_core.messages import HumanMessage

from utils.llm import get_llm, DEFAULT_MODEL

_CHROMA_DIR = Path(
    os.environ.get("CHROMA_DIR")
    or str(Path(__file__).parent.parent.parent / "vector_db" / "chroma")
)
_COLLECTION = "pdf_court_cases"

# case_type 영문→한글 매핑 (court.py SearchRequest 호환)
_CASE_TYPE_MAP = {
    "CRIMINAL": "형사",
    "ADMIN": "행정",
    "criminal": "형사",
    "admin": "행정",
}


def _get_col():
    import chromadb
    from db.chroma_search import _get_ef
    client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
    return client.get_collection(_COLLECTION, embedding_function=_get_ef())


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_court_stats() -> str:
    """법원 PDF 판례 DB 현황을 반환합니다."""
    try:
        col = _get_col()
        total = col.count()
        sample = col.get(limit=total, include=["metadatas"])
        courts: dict = {}
        tax_types: dict = {}
        for m in sample["metadatas"] or []:
            c = m.get("court", "기타")
            tt = m.get("tax_type", "기타")
            courts[c] = courts.get(c, 0) + 1
            tax_types[tt] = tax_types.get(tt, 0) + 1
        top_c = sorted(courts.items(), key=lambda x: -x[1])[:5]
        top_tt = sorted(tax_types.items(), key=lambda x: -x[1])[:5]
        lines = [
            f"총 {total:,}건의 법원 판례(PDF 원문) 보유",
            "",
            "주요 법원 (상위 5):",
            *[f"  {k}: {v}건" for k, v in top_c],
            "",
            "주요 사건 유형:",
            *[f"  {k}: {v}건" for k, v in top_tt],
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"통계 조회 실패: {e}"


@tool
def search_court_cases(query: str, case_type: str = "", court: str = "", n_results: int = 8) -> str:
    """법원 PDF 판례를 벡터 검색합니다.

    Args:
        query: 검색 쿼리
        case_type: 사건 유형 필터 (CRIMINAL/형사, ADMIN/행정, 또는 빈 문자열)
        court: 법원명 필터 (선택)
        n_results: 반환 건수 (기본 8)
    """
    try:
        col = _get_col()
        # 한글 매핑
        mapped_type = _CASE_TYPE_MAP.get(case_type, case_type)
        filters = []
        if mapped_type:
            filters.append({"tax_type": {"$eq": mapped_type}})
        if court:
            filters.append({"court": {"$eq": court}})
        where = None
        if len(filters) == 1:
            where = filters[0]
        elif len(filters) > 1:
            where = {"$and": filters}

        kwargs = {"query_texts": [query], "n_results": min(n_results, col.count())}
        if where:
            kwargs["where"] = where
        res = col.query(**kwargs, include=["metadatas", "documents", "distances"])

        lines = []
        for i, doc_id in enumerate(res["ids"][0]):
            m = (res["metadatas"][0][i] if res["metadatas"] else {}) or {}
            doc = (res["documents"][0][i] if res["documents"] else "") or ""
            dist = res["distances"][0][i] if res["distances"] else None
            sim = f"{(1 - dist) * 100:.0f}%" if dist is not None else "N/A"
            lines.append(
                f"[{i+1}] {m.get('case_no', '')} | {m.get('court', '')} | "
                f"{m.get('tax_type', '')} | 유사도 {sim}\n"
                f"    ID: {m.get('case_id', doc_id)}\n"
                f"    내용: {doc[:150]}"
            )
        return "\n\n".join(lines) if lines else "검색 결과 없음"
    except Exception as e:
        return f"검색 실패: {e}"


@tool
def get_case_detail(case_id: str) -> str:
    """특정 법원 판례 전문을 조회합니다.

    Args:
        case_id: 판례 ID (case_id 메타데이터 값)
    """
    try:
        col = _get_col()
        r = col.get(where={"case_id": {"$eq": case_id}}, include=["metadatas", "documents"])
        if not r["ids"]:
            return f"'{case_id}' 판례를 찾을 수 없습니다."
        m = (r["metadatas"][0] if r["metadatas"] else {}) or {}
        doc = (r["documents"][0] if r["documents"] else "") or ""
        lines = [
            f"사건번호: {m.get('case_no', '')}",
            f"법원: {m.get('court', '')}",
            f"유형: {m.get('tax_type', '')}",
            f"ID: {case_id}",
            "",
            "【판례 전문】",
            doc,
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"조회 실패: {e}"


@tool
def analyze_case_trend(case_type: str = "", year: str = "") -> str:
    """법원 판례 트렌드를 분석합니다.

    Args:
        case_type: 사건 유형 필터 (선택)
        year: 연도 필터 (선택, 예: "2023")
    """
    try:
        col = _get_col()
        mapped_type = _CASE_TYPE_MAP.get(case_type, case_type)
        where = None
        if mapped_type:
            where = {"tax_type": {"$eq": mapped_type}}

        kwargs = {"limit": min(500, col.count()), "include": ["metadatas"]}
        if where:
            kwargs["where"] = where
        sample = col.get(**kwargs)

        courts: dict = {}
        types: dict = {}
        for m in sample["metadatas"] or []:
            c = m.get("court", "기타")
            t = m.get("tax_type", "기타")
            courts[c] = courts.get(c, 0) + 1
            types[t] = types.get(t, 0) + 1

        lines = [
            f"분석 대상: {len(sample['ids'])}건",
            "",
            "법원별 분포:",
            *[f"  {k}: {v}건" for k, v in sorted(courts.items(), key=lambda x: -x[1])[:8]],
            "",
            "사건 유형별:",
            *[f"  {k}: {v}건" for k, v in sorted(types.items(), key=lambda x: -x[1])[:5]],
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"트렌드 분석 실패: {e}"


@tool
def find_similar_cases(fact_summary: str, case_type: str = "", n: int = 5) -> str:
    """의뢰인 사건 사실관계와 유사한 판례를 검색합니다.

    Args:
        fact_summary: 사건 사실관계 요약
        case_type: 사건 유형 필터 (선택)
        n: 반환 건수
    """
    return search_court_cases.invoke({
        "query": fact_summary,
        "case_type": case_type,
        "court": "",
        "n_results": n,
    })


# ── LLM Agent ─────────────────────────────────────────────────────────────────

_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = get_llm(model=DEFAULT_MODEL, temperature=0)
    return _llm


class CourtAgent:
    """법원 판례 자연어 질문 에이전트."""

    def ask(self, question: str) -> str:
        # 관련 판례 검색
        search_result = search_court_cases.invoke({
            "query": question,
            "case_type": "",
            "court": "",
            "n_results": 5,
        })

        prompt = (
            "당신은 조세·형사·행정 법원 판례 전문가다.\n"
            "아래 관련 판례를 참고하여 질문에 답변하라.\n\n"
            f"[관련 판례]\n{search_result}\n\n"
            f"[질문]\n{question}\n\n"
            "판례 사실관계, 법리, 시사점을 중심으로 명확하게 답변하라."
        )
        resp = _get_llm().invoke([HumanMessage(content=prompt)])
        return resp.content
