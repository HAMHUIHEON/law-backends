# agents/trend_agent.py
"""
TrendAgent — 판례 트렌드 에이전트

쟁점 키워드와 기간을 입력하면 연도별 납세자 승소율을 집계하고
법리 변천사를 서술합니다.
"""

import json
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage
from utils.llm import get_llm, DEFAULT_MODEL
from langgraph.graph import END, StateGraph

from db.graph_search import LegalGraphSearch

_llm = get_llm(model=DEFAULT_MODEL, temperature=0)


class TrendState(TypedDict):
    query: str
    start_year: int
    end_year: int

    trend_data: Optional[dict]
    final_report: Optional[str]


# ── 1. DataCollector ──────────────────────────────────────────────────────────

def data_collector_node(state: TrendState) -> dict:
    searcher = LegalGraphSearch()
    try:
        data = searcher.get_trend_data(
            query=state["query"],
            start_year=state["start_year"],
            end_year=state["end_year"],
            top_k=50,
        )
    finally:
        searcher.close()
    return {"trend_data": data}


# ── 2. TrendAnalyzer ──────────────────────────────────────────────────────────

def trend_analyzer_node(state: TrendState) -> dict:
    data = state.get("trend_data") or {}
    year_stats = data.get("year_stats") or {}
    total = data.get("total_cases", 0)

    if total == 0:
        return {
            "final_report": (
                f"'{state['query']}' 관련 판례 데이터가 없습니다. "
                "다른 검색어를 시도해보세요."
            )
        }

    stats_str = json.dumps(year_stats, ensure_ascii=False, indent=2)
    issues_sample = json.dumps(
        (data.get("similar_issues") or [])[:5], ensure_ascii=False, indent=2
    )

    prompt = (
        "당신은 조세법 전문 리서치 애널리스트다.\n"
        "아래 판례 통계 데이터를 바탕으로 트렌드 분석 보고서를 작성하라.\n\n"
        f"[분석 쟁점]\n{state['query']}\n\n"
        f"[분석 기간]\n{state['start_year']}년 ~ {state['end_year']}년\n\n"
        f"[연도별 납세자 승소율 통계]\n{stats_str}\n\n"
        f"[대표 유사 쟁점 판례 (5건)]\n{issues_sample}\n\n"
        "다음 구조로 보고서를 작성하라:\n\n"
        "## 분석 개요\n"
        f"총 {total}건 판례 분석\n\n"
        "## 연도별 트렌드\n"
        "연도별 승소율 변화를 서술 (상승/하락 구간, 전환점)\n\n"
        "## 법리 변천사\n"
        "판례 내용을 기반으로 법원의 판단 기준이 어떻게 변했는지 서술\n\n"
        "## 최근 트렌드 진단\n"
        "최근 3~5년의 흐름이 납세자에게 유리한가 불리한가\n\n"
        "## 실무 시사점\n"
        "이 트렌드를 어떻게 활용할 것인가"
    )

    resp = _llm.invoke([HumanMessage(content=prompt)])
    return {"final_report": resp.content}


# ── Graph ─────────────────────────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(TrendState)
    g.add_node("data_collector", data_collector_node)
    g.add_node("trend_analyzer", trend_analyzer_node)

    g.set_entry_point("data_collector")
    g.add_edge("data_collector", "trend_analyzer")
    g.add_edge("trend_analyzer", END)
    return g.compile()


class TrendAgent:
    """
    판례 트렌드 분석

    result = agent.run(query="부당행위계산 부인", start_year=2015, end_year=2025)
    result["final_report"]  # 트렌드 보고서 (str)
    result["trend_data"]    # 연도별 통계 원본
    """

    def __init__(self):
        self.graph = _build_graph()

    def run(self, query: str, start_year: int = 2000, end_year: int = 2030) -> dict:
        initial: TrendState = {
            "query": query,
            "start_year": start_year,
            "end_year": end_year,
            "trend_data": None,
            "final_report": None,
        }
        return self.graph.invoke(initial)
