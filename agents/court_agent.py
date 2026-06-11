"""
법원 판례 에이전트

CASE/ PDF 추출본 + DRF API 수집본을 기반으로 법원 판례를 검색·분석합니다.
bravo 파이프라인 캐시(narrative, issue_logic)를 활용해 구조화된 분석 제공.

사용:
    from agents.court_agent import CourtAgent

    agent = CourtAgent()
    response = agent.ask("국제조세 이전가격 관련 납세자 승소 판례 찾아줘")
    response = agent.ask("조세범처벌법 포탈죄 무죄 판결 사례가 있나요?")
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Iterator, Optional

from dotenv import load_dotenv
load_dotenv()

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from utils.llm import get_llm

ROOT       = Path(__file__).parent.parent
PDF_DIR    = ROOT / "cases" / "court"
API_DIR    = ROOT / "cases" / "court_api"
CACHE_DIR  = ROOT / "cache"
CHROMA_DIR = ROOT / "chroma_db"


SYSTEM_PROMPT = """\
당신은 한국 세법 전문 법원 판례 분석 에이전트입니다.
조세범처벌법(형사 사건)과 국제조세·이전가격·법인세 등 행정소송(취소소송) 판례를
전문적으로 검색하고 분석합니다.

판례 검색 시 반드시 search_court_cases 도구를 먼저 사용하세요.
분석 결과는 다음 형식으로 제공합니다:
- 관련 판례 목록 (법원, 사건번호, 핵심 쟁점, 결과)
- 판결 패턴 분석
- 납세자 관점의 실무 시사점

사건 유형:
- CRIMINAL: 조세범처벌법 위반 (도/노/고합 번호)
- ADMIN: 행정소송 — 과세처분 취소 청구 (두/누/구합 번호)
"""


# ── Chroma 컬렉션 ─────────────────────────────────────────────────────────────

def _get_collection():
    import chromadb
    from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

    ef = OpenAIEmbeddingFunction(
        api_key=os.environ["OPENAI_API_KEY"],
        model_name="text-embedding-3-small",
    )
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_collection("court_cases", embedding_function=ef)


def _load_cache_data(case_id: str) -> dict:
    base = CACHE_DIR / case_id
    out: dict = {}
    for fname in ("narrative.json", "issue_logic.json", "metadata.json"):
        p = base / fname
        if p.exists():
            try:
                out[fname.replace(".json", "")] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return out


def _format_result(doc: str, meta: dict, cache: dict = {}) -> str:
    parts = []
    court    = meta.get("court", "")
    case_no  = meta.get("case_no", "")
    case_type = meta.get("case_type", "")
    parts.append(f"[{court}] {case_no} ({case_type})")

    narrative = cache.get("narrative", {})
    if narrative.get("fact_summary"):
        parts.append(f"사실관계: {narrative['fact_summary'][:300]}")
    if narrative.get("core_conflicts"):
        parts.append("핵심쟁점: " + " / ".join(narrative["core_conflicts"][:3]))

    issue_log = cache.get("issue_logic", {})
    chains = issue_log.get("issue_logic_chains", []) if isinstance(issue_log, dict) else []
    if chains:
        issues = [c.get("issue", "") for c in chains[:3] if isinstance(c, dict)]
        parts.append("쟁점체인: " + " → ".join(i for i in issues if i))

    if not narrative:
        parts.append(doc[:400])

    return "\n".join(parts)


# ── 도구 정의 ──────────────────────────────────────────────────────────────────

@tool
def search_court_cases(query: str, case_type: str = "", court: str = "", n_results: int = 8) -> str:
    """
    법원 판례 벡터 검색.

    Args:
        query: 검색 쿼리 (예: "이전가격 독립기업원칙", "조세포탈 고의")
        case_type: "CRIMINAL" (형사) | "ADMIN" (행정소송) | "" (전체)
        court: 법원명 필터 (예: "대법원", "" = 전체)
        n_results: 반환 건수 (기본 8)
    """
    try:
        col = _get_collection()
    except Exception as e:
        return f"[벡터 DB 미준비] {e}"

    where: dict = {}
    if case_type:
        where["case_type"] = {"$eq": case_type}
    if court:
        where["court"] = {"$eq": court}

    kwargs: dict = {"query_texts": [query], "n_results": min(n_results, col.count() or 1)}
    if where:
        kwargs["where"] = where

    res = col.query(**kwargs)
    docs  = res["documents"][0]
    metas = res["metadatas"][0]

    if not docs:
        return "검색 결과 없음."

    lines = []
    for i, (doc, meta) in enumerate(zip(docs, metas), 1):
        case_id = meta.get("case_id", "")
        cache   = _load_cache_data(case_id) if case_id else {}
        lines.append(f"\n--- {i} ---")
        lines.append(_format_result(doc, meta, cache))

    return "\n".join(lines)


@tool
def get_case_detail(case_id: str) -> str:
    """
    특정 판례의 전체 분석 결과 조회.

    Args:
        case_id: 예) "대법원_2022두13402", "api_12345678"
    """
    # PDF 기반
    pdf_path = PDF_DIR / f"{case_id}.json"
    if pdf_path.exists():
        data = json.loads(pdf_path.read_text(encoding="utf-8"))
        cache = _load_cache_data(case_id)
        parts = [f"=== {case_id} ==="]
        parts.append(f"법원: {data.get('court')}  유형: {data.get('case_type')}  연도: {data.get('year')}")

        narrative = cache.get("narrative", {})
        if narrative:
            parts.append(f"\n[사실관계]\n{narrative.get('fact_summary', '')[:800]}")
            for arg in narrative.get("plaintiff_arguments", [])[:3]:
                parts.append(f"  원고(납세자): {arg}")
            for arg in narrative.get("defendant_arguments", [])[:3]:
                parts.append(f"  피고(과세관청): {arg}")
            for r in narrative.get("court_reasoning", [])[:3]:
                parts.append(f"  법원 판단: {r}")

        issue_log = cache.get("issue_logic", {})
        chains = issue_log.get("issue_logic_chains", []) if isinstance(issue_log, dict) else []
        if chains:
            parts.append("\n[쟁점 논리 체인]")
            for c in chains[:3]:
                if isinstance(c, dict):
                    parts.append(f"  쟁점: {c.get('issue', '')}")
                    parts.append(f"  결론: {c.get('mini_conclusion', '')}")

        return "\n".join(parts)

    # API 기반
    api_id = case_id.replace("api_", "")
    api_path = API_DIR / f"{api_id}.json"
    if api_path.exists():
        data = json.loads(api_path.read_text(encoding="utf-8"))
        parts = [f"=== {case_id} ==="]
        parts.append(f"{data.get('법원명')} {data.get('사건번호')} {data.get('선고일자')}")
        parts.append(f"\n[판시사항]\n{data.get('판시사항', '')[:600]}")
        parts.append(f"\n[판결요지]\n{data.get('판결요지', '')[:600]}")
        parts.append(f"\n[참조조문]\n{data.get('참조조문', '')}")
        return "\n".join(parts)

    return f"판례 {case_id}를 찾을 수 없습니다."


@tool
def analyze_case_trend(case_type: str = "", year: str = "") -> str:
    """
    판례 트렌드 분석.

    Args:
        case_type: "CRIMINAL" | "ADMIN" | "" (전체)
        year: 연도 필터 (예: "2020") | "" (전체)
    """
    pdf_files = sorted(PDF_DIR.glob("*.json")) if PDF_DIR.exists() else []

    year_counter: Counter = Counter()
    court_counter: Counter = Counter()
    type_counter: Counter = Counter()

    for f in pdf_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue

        ct = data.get("case_type", "")
        yr = data.get("year", "")
        co = data.get("court", "")

        if case_type and ct != case_type:
            continue
        if year and yr != year:
            continue

        year_counter[yr] += 1
        court_counter[co] += 1
        type_counter[ct] += 1

    if not year_counter:
        return "해당 조건의 판례 없음."

    lines = [f"=== 판례 트렌드 분석 (case_type={case_type or '전체'}, year={year or '전체'}) ==="]
    lines.append(f"\n총 {sum(year_counter.values())}건")

    lines.append("\n[연도별]")
    for yr, cnt in sorted(year_counter.items()):
        lines.append(f"  {yr}: {cnt}건")

    lines.append("\n[법원별 Top 10]")
    for co, cnt in court_counter.most_common(10):
        lines.append(f"  {co}: {cnt}건")

    lines.append("\n[유형별]")
    for ct, cnt in type_counter.most_common():
        lines.append(f"  {ct}: {cnt}건")

    return "\n".join(lines)


@tool
def find_similar_cases(fact_summary: str, case_type: str = "", n: int = 5) -> str:
    """
    의뢰인 사건 사실관계와 유사한 판례 검색.

    Args:
        fact_summary: 의뢰인 사건 사실관계 요약
        case_type: "CRIMINAL" | "ADMIN" | ""
        n: 반환 건수
    """
    return search_court_cases.invoke({
        "query": fact_summary,
        "case_type": case_type,
        "court": "",
        "n_results": n,
    })


@tool
def get_court_stats() -> str:
    """법원 판례 DB 통계."""
    pdf_count = len(list(PDF_DIR.glob("*.json"))) if PDF_DIR.exists() else 0
    api_count = len(list(API_DIR.glob("*.json"))) if API_DIR.exists() else 0

    try:
        col = _get_collection()
        chroma_count = col.count()
    except Exception:
        chroma_count = 0

    return (
        f"PDF 추출본: {pdf_count}건\n"
        f"DRF API 수집본: {api_count}건\n"
        f"벡터 DB (court_cases): {chroma_count}건"
    )


# ── 에이전트 클래스 ────────────────────────────────────────────────────────────

TOOLS = [
    search_court_cases,
    get_case_detail,
    analyze_case_trend,
    find_similar_cases,
    get_court_stats,
]


class CourtAgent:
    def __init__(self):
        self.llm = get_llm(model=MODEL, temperature=0)
        self._bound = self.llm.bind_tools(TOOLS)
        self._tool_map = {t.name: t for t in TOOLS}
        self._history: list = [SystemMessage(content=SYSTEM_PROMPT)]

    def ask(self, question: str) -> str:
        self._history.append(HumanMessage(content=question))
        for _ in range(6):
            resp = self._bound.invoke(self._history)
            self._history.append(resp)
            if not resp.tool_calls:
                return resp.content
            for tc in resp.tool_calls:
                t = self._tool_map.get(tc["name"])
                if t:
                    result = t.invoke(tc["args"])
                else:
                    result = f"[알 수 없는 도구: {tc['name']}]"
                from langchain_core.messages import ToolMessage
                self._history.append(
                    ToolMessage(content=str(result), tool_call_id=tc["id"])
                )
        return self._history[-1].content if self._history else ""

    def stream(self, question: str) -> Iterator[str]:
        self._history.append(HumanMessage(content=question))
        for _ in range(6):
            resp = self._bound.invoke(self._history)
            self._history.append(resp)
            if not resp.tool_calls:
                yield resp.content
                return
            for tc in resp.tool_calls:
                t = self._tool_map.get(tc["name"])
                result = t.invoke(tc["args"]) if t else f"[알 수 없는 도구]"
                from langchain_core.messages import ToolMessage
                self._history.append(
                    ToolMessage(content=str(result), tool_call_id=tc["id"])
                )

    def reset(self):
        self._history = [SystemMessage(content=SYSTEM_PROMPT)]


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "법원 판례 DB 통계 알려줘"
    agent = CourtAgent()
    print(agent.ask(q))
