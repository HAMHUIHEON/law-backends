# agents/strategy_agent.py
"""
StrategyAgent — 의뢰인 사건 전략 에이전트

의뢰인이 제출한 사건 요약을 받아 유사 판례를 분석하고
경정청구 / 조세심판 / 소송 중 최적 전략을 권고합니다.

LangGraph: FactExtractor → CaseSearcher → PatternAnalyzer → Strategist
"""

import json
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from langgraph.graph import END, StateGraph

from db.graph_search import LegalGraphSearch

_llm = ChatOpenAI(model="gpt-4.1", temperature=0)


class StrategyState(TypedDict):
    client_summary: str

    # FactExtractor 출력
    key_facts: str
    legal_issues: list[str]
    tax_type: str                # 소득세, 법인세, 부가세, 국제조세 등

    # CaseSearcher 출력
    similar_cases: Optional[list]
    pattern_data: Optional[dict]

    # Strategist 출력
    final_report: Optional[str]


# ── 1. FactExtractor ──────────────────────────────────────────────────────────

def fact_extractor_node(state: StrategyState) -> dict:
    prompt = (
        "당신은 세무·법률 전문가다. 아래 의뢰인 사건 요약을 분석해 JSON으로만 반환하라.\n\n"
        f"사건 요약:\n{state['client_summary']}\n\n"
        "반환 형식 (JSON만, 다른 텍스트 없음):\n"
        '{"key_facts": "핵심 사실관계 요약 (3~5문장)", '
        '"legal_issues": ["쟁점 1", "쟁점 2"], '
        '"tax_type": "세목 (예: 법인세, 소득세, 부가가치세, 국제조세, 조세범처벌)"}'
    )
    resp = _llm.invoke([HumanMessage(content=prompt)])
    try:
        data = json.loads(resp.content.strip())
    except Exception:
        data = {"key_facts": state["client_summary"], "legal_issues": [state["client_summary"]], "tax_type": "미분류"}

    return {
        "key_facts": data.get("key_facts", ""),
        "legal_issues": data.get("legal_issues") or [state["client_summary"]],
        "tax_type": data.get("tax_type", "미분류"),
    }


# ── 2. CaseSearcher ───────────────────────────────────────────────────────────

def case_searcher_node(state: StrategyState) -> dict:
    searcher = LegalGraphSearch()
    try:
        combined_query = " ".join(state["legal_issues"])
        similar = searcher.search_similar_issues(combined_query, top_k=10)
        pattern = searcher.analyze_winning_patterns(combined_query, top_k=10)
    finally:
        searcher.close()

    return {
        "similar_cases": similar,
        "pattern_data": pattern,
    }


# ── 3. Strategist ─────────────────────────────────────────────────────────────

def strategist_node(state: StrategyState) -> dict:
    cases_str = json.dumps(state.get("similar_cases") or [], ensure_ascii=False, indent=2)
    pattern_str = json.dumps(state.get("pattern_data") or {}, ensure_ascii=False, indent=2)

    prompt = (
        "당신은 국세청 경력 10년의 세무사 겸 조세전문 변호사다.\n"
        "아래 의뢰인 사건 정보와 유사 판례 분석 결과를 바탕으로 전략 보고서를 작성하라.\n\n"
        f"[의뢰인 사건 요약]\n{state['client_summary']}\n\n"
        f"[핵심 사실관계]\n{state['key_facts']}\n\n"
        f"[주요 쟁점]\n" + "\n".join(f"- {i}" for i in state["legal_issues"]) + "\n\n"
        f"[유사 판례 목록]\n{cases_str}\n\n"
        f"[승소 패턴 분석]\n{pattern_str}\n\n"
        "다음 구조로 보고서를 작성하라:\n\n"
        "## 사건 개요\n"
        "## 핵심 쟁점\n"
        "## 유사 판례 분석\n"
        "  - 판례번호, 결론, 이 사건과의 유사점/차이점\n"
        "## 전략 권고\n"
        "  ### 경정청구 (가능 여부, 기한, 승산)\n"
        "  ### 조세심판 (강·약점)\n"
        "  ### 행정소송 (강·약점)\n"
        "  ### 최종 권고: 어떤 경로를 먼저 선택해야 하는가\n"
        "## 리스크 포인트\n"
        "## 즉시 준비해야 할 증거·서류"
    )

    resp = _llm.invoke([HumanMessage(content=prompt)])
    return {"final_report": resp.content}


# ── Graph ─────────────────────────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(StrategyState)
    g.add_node("fact_extractor", fact_extractor_node)
    g.add_node("case_searcher", case_searcher_node)
    g.add_node("strategist", strategist_node)

    g.set_entry_point("fact_extractor")
    g.add_edge("fact_extractor", "case_searcher")
    g.add_edge("case_searcher", "strategist")
    g.add_edge("strategist", END)
    return g.compile()


class StrategyAgent:
    """
    의뢰인 사건 요약 → 유사 판례 검색 → 전략 권고 (경정청구/심판/소송)

    result = agent.run(client_summary="...")
    result["final_report"]   # 전략 보고서 (str)
    result["similar_cases"]  # 유사 판례 목록
    result["pattern_data"]   # 승소 패턴 분석
    """

    def __init__(self):
        self.graph = _build_graph()

    def run(self, client_summary: str) -> dict:
        initial: StrategyState = {
            "client_summary": client_summary,
            "key_facts": "",
            "legal_issues": [],
            "tax_type": "",
            "similar_cases": None,
            "pattern_data": None,
            "final_report": None,
        }
        return self.graph.invoke(initial)
