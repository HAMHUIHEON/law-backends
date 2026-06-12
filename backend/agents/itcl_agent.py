# agents/itcl_agent.py
"""
ITCLAgent — 이전가격(국제조세) 전문 에이전트

특수관계자 거래 정보를 입력하면 정상가격 산출 방법 판단 + 리스크 평가를 반환합니다.

데이터 소스:
  - Chroma taxlaw_prec: 이전가격 관련 법원 판례 32,628건
  - Chroma law_articles: 국제조세조정법·세법 조문 6,687건
  - Neo4j ITCLSearch: ITCL IntegratedSnapshot (65개 버전, 법령 구조 그래프)

LangGraph: Searcher → ITCLAnalyzer
"""

import json
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage
from utils.llm import get_llm, DEFAULT_MODEL
from langgraph.graph import END, StateGraph

_llm = None

ITCL_SYSTEM = (
    "당신은 국제조세·이전가격 전문 세무사다. "
    "OECD 이전가격 지침, 국제조세조정에 관한 법률, 관련 판례에 정통하다. "
    "정상가격 산출 방법(CUP, RPM, COST+, TNMM, PSM)의 적용 기준을 명확히 알고 있다."
)


def _get_llm():
    global _llm
    if _llm is None:
        _llm = get_llm(model=DEFAULT_MODEL, temperature=0)
    return _llm


class ITCLState(TypedDict):
    query: str

    court_cases: Optional[list]
    law_articles: Optional[list]
    itcl_issues: Optional[list]

    final_report: Optional[str]


# ── 1. Searcher ───────────────────────────────────────────────────────────────

def searcher_node(state: ITCLState) -> dict:
    from db.chroma_search import search_taxlaw_prec, search_law_articles

    itcl_query = f"이전가격 특수관계자 국제조세 {state['query']}"

    court_cases = search_taxlaw_prec(itcl_query, n=8)
    law_articles = search_law_articles(itcl_query, n=6)

    # ITCLSearch (Neo4j ITCL 그래프) — 실패 시 graceful 처리
    itcl_issues = []
    try:
        from db.itcl_search import ITCLSearch
        itcl = ITCLSearch()
        itcl_issues = itcl.search_issues(state["query"], top_k=5) or []
        itcl.close()
    except Exception:
        pass

    return {
        "court_cases": court_cases,
        "law_articles": law_articles,
        "itcl_issues": itcl_issues,
    }


# ── 2. ITCLAnalyzer ───────────────────────────────────────────────────────────

def analyzer_node(state: ITCLState) -> dict:
    cases_str = json.dumps(state.get("court_cases") or [], ensure_ascii=False, indent=2)
    law_str = json.dumps(state.get("law_articles") or [], ensure_ascii=False, indent=2)
    issues_str = json.dumps(state.get("itcl_issues") or [], ensure_ascii=False, indent=2)

    prompt = (
        f"{ITCL_SYSTEM}\n\n"
        "아래 정보를 바탕으로 이전가격 분석 보고서를 작성하라.\n\n"
        f"[질의/거래 정보]\n{state['query']}\n\n"
        f"[관련 법원 판례]\n{cases_str}\n\n"
        f"[국제조세조정법 관련 세법 조문]\n{law_str}\n\n"
        f"[ITCL 법령 쟁점 (Neo4j)]\n{issues_str}\n\n"
        "다음 구조로 보고서를 작성하라:\n\n"
        "## 거래 개요 및 쟁점\n\n"
        "## 정상가격 산출 방법 검토\n"
        "  ### CUP (비교 가능 비통제 가격법)\n"
        "  ### RPM (재판매 가격법)\n"
        "  ### COST+ (원가 가산법)\n"
        "  ### TNMM (거래순이익률법)\n"
        "  ### PSM (이익 분할법)\n"
        "  → 이 거래에 적합한 방법 권고\n\n"
        "## 관련 판례 시사점\n"
        "  유사 거래에서 법원이 어떤 방법을 인정했는지\n\n"
        "## 법령 근거\n"
        "  국제조세조정법 관련 조문\n\n"
        "## 리스크 평가\n"
        "  - 과세관청이 문제 삼을 가능성이 높은 부분\n"
        "  - 이전가격 조사 대비 체크리스트\n\n"
        "## 권고 사항"
    )

    resp = _get_llm().invoke([HumanMessage(content=prompt)])
    return {"final_report": resp.content}


# ── Graph ─────────────────────────────────────────────────────────────────────

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        g = StateGraph(ITCLState)
        g.add_node("searcher", searcher_node)
        g.add_node("analyzer", analyzer_node)
        g.set_entry_point("searcher")
        g.add_edge("searcher", "analyzer")
        g.add_edge("analyzer", END)
        _graph = g.compile()
    return _graph


class ITCLAgent:
    """
    이전가격·국제조세 전문 분석

    result = agent.run(query="A사가 해외 특수관계법인에 제품을 시가보다 낮은 가격으로 공급...")
    result["final_report"]  # 이전가격 분석 보고서 (str)
    result["court_cases"]   # 관련 판례
    result["law_articles"]  # 관련 조문
    result["itcl_issues"]   # ITCL 법령 쟁점 (Neo4j)
    """

    def run(self, query: str) -> dict:
        initial: ITCLState = {
            "query": query,
            "court_cases": None,
            "law_articles": None,
            "itcl_issues": None,
            "final_report": None,
        }
        return _get_graph().invoke(initial)
