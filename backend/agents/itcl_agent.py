# agents/itcl_agent.py
"""
ITCLAgent — 이전가격(국제조세) 전문 에이전트

SupervisorAgent 기반이지만 국제조세조정법·이전가격 특화 시스템 프롬프트를 사용합니다.
특수관계자 거래 정보를 입력하면 정상가격 산출 방법 판단 + 리스크 평가를 반환합니다.
"""

import json
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage
from utils.llm import get_llm, DEFAULT_MODEL
from langgraph.graph import END, StateGraph

from db.graph_search import LegalGraphSearch
from db.itcl_search import ITCLSearch

_llm = get_llm(model=DEFAULT_MODEL, temperature=0)

ITCL_SYSTEM = (
    "당신은 국제조세·이전가격 전문 세무사다. "
    "OECD 이전가격 지침, 국제조세조정에 관한 법률, 관련 판례에 정통하다. "
    "정상가격 산출 방법(CUP, RPM, COST+, TNMM, PSM)의 적용 기준을 명확히 알고 있다."
)


class ITCLState(TypedDict):
    query: str

    case_results: Optional[list]
    law_issues: Optional[list]
    law_articles: Optional[list]

    final_report: Optional[str]


# ── 1. ParallelSearcher ───────────────────────────────────────────────────────

def searcher_node(state: ITCLState) -> dict:
    # 판례 검색
    g_searcher = LegalGraphSearch()
    try:
        itcl_query = f"이전가격 특수관계자 국제조세 {state['query']}"
        case_results = g_searcher.search_similar_issues(itcl_query, top_k=8)
    finally:
        g_searcher.close()

    # ITCL 법령 검색
    try:
        itcl = ITCLSearch()
        law_issues = itcl.search_issues(state["query"], top_k=5)
        law_articles = []
        for issue in law_issues[:2]:
            arts = itcl.get_articles_for_issue(issue.get("issue_id") or "")
            law_articles.extend(arts)
        itcl.close()
    except Exception:
        law_issues = []
        law_articles = []

    return {
        "case_results": case_results,
        "law_issues": law_issues,
        "law_articles": law_articles,
    }


# ── 2. ITCLAnalyzer ───────────────────────────────────────────────────────────

def analyzer_node(state: ITCLState) -> dict:
    cases_str = json.dumps(state.get("case_results") or [], ensure_ascii=False, indent=2)
    issues_str = json.dumps(state.get("law_issues") or [], ensure_ascii=False, indent=2)
    articles_str = json.dumps(state.get("law_articles") or [], ensure_ascii=False, indent=2)

    prompt = (
        f"{ITCL_SYSTEM}\n\n"
        "아래 정보를 바탕으로 이전가격 분석 보고서를 작성하라.\n\n"
        f"[질의/거래 정보]\n{state['query']}\n\n"
        f"[관련 판례]\n{cases_str}\n\n"
        f"[국제조세조정법 관련 쟁점]\n{issues_str}\n\n"
        f"[관련 조문]\n{articles_str}\n\n"
        "다음 구조로 보고서를 작성하라:\n\n"
        "## 거래 개요 및 쟁점\n\n"
        "## 정상가격 산출 방법 검토\n"
        "  ### CUP (비교 가능 비통제 가격법)\n"
        "  ### RPM (재판매 가격법)\n"
        "  ### COST+ (원가 가산법)\n"
        "  ### TNMM (거래순이익률법) ← 가장 일반적으로 채택\n"
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

    resp = _llm.invoke([HumanMessage(content=prompt)])
    return {"final_report": resp.content}


# ── Graph ─────────────────────────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(ITCLState)
    g.add_node("searcher", searcher_node)
    g.add_node("analyzer", analyzer_node)

    g.set_entry_point("searcher")
    g.add_edge("searcher", "analyzer")
    g.add_edge("analyzer", END)
    return g.compile()


class ITCLAgent:
    """
    이전가격·국제조세 전문 분석

    result = agent.run(query="A사가 해외 특수관계법인에 제품을 시가보다 낮은 가격으로 공급...")
    result["final_report"]  # 이전가격 분석 보고서 (str)
    result["case_results"]  # 관련 판례
    result["law_articles"]  # 관련 조문
    """

    def __init__(self):
        self.graph = _build_graph()

    def run(self, query: str) -> dict:
        initial: ITCLState = {
            "query": query,
            "case_results": None,
            "law_issues": None,
            "law_articles": None,
            "final_report": None,
        }
        return self.graph.invoke(initial)
