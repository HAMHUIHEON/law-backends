# agents/risk_agent.py
"""
RiskAgent — 법령 개정 리스크 알림 에이전트

새 법령 개정 내용을 입력하면
해당 법령을 인용한 기존 판례들이 개정 후에도 유효한지 재평가하고
리스크 요약 리포트를 생성합니다.
"""

import json
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from langgraph.graph import END, StateGraph

from db.graph_search import LegalGraphSearch

_llm = ChatOpenAI(model="gpt-4.1", temperature=0)


class RiskState(TypedDict):
    statute_name: str        # 개정된 법령명 (예: "법인세법")
    revision_summary: str    # 개정 내용 요약
    effective_date: str      # 시행일 (예: "2025-01-01")

    affected_cases: Optional[list]
    final_report: Optional[str]


# ── 1. CaseFinder ─────────────────────────────────────────────────────────────

def case_finder_node(state: RiskState) -> dict:
    searcher = LegalGraphSearch()
    try:
        cases = searcher.get_statute_cases(state["statute_name"])
    finally:
        searcher.close()
    return {"affected_cases": cases}


# ── 2. RiskEvaluator ──────────────────────────────────────────────────────────

def risk_evaluator_node(state: RiskState) -> dict:
    cases = state.get("affected_cases") or []
    if not cases:
        return {
            "final_report": (
                f"'{state['statute_name']}' 관련 판례 데이터가 없습니다.\n"
                "법령명을 공식 명칭으로 입력하세요 (예: '국세기본법', '법인세법')."
            )
        }

    cases_str = json.dumps(cases[:20], ensure_ascii=False, indent=2)

    prompt = (
        "당신은 세무·법률 전문가다. 법령 개정이 기존 판례들에 미치는 영향을 분석하라.\n\n"
        f"[개정 법령]\n{state['statute_name']}\n\n"
        f"[개정 내용]\n{state['revision_summary']}\n\n"
        f"[시행일]\n{state['effective_date']}\n\n"
        f"[해당 법령 인용 판례 목록]\n{cases_str}\n\n"
        "다음 구조로 리스크 보고서를 작성하라:\n\n"
        "## 개정 내용 요약\n\n"
        "## 영향 받는 판례 분류\n"
        "  ### 🔴 고위험: 판례 결론이 개정 후 무효화될 수 있는 경우\n"
        "  ### 🟡 주의: 판례 법리를 조정해야 할 수 있는 경우\n"
        "  ### 🟢 영향 없음: 개정과 무관한 쟁점의 판례\n\n"
        "## 핵심 리스크 포인트\n"
        "  개정 후 가장 주의해야 할 3가지\n\n"
        "## 실무 대응 방안\n"
        "  - 개정 전 처분 건: 경정청구 가능성\n"
        "  - 개정 후 신규 거래: 변경해야 할 사항\n"
        "  - 세무조사 대비 체크리스트"
    )

    resp = _llm.invoke([HumanMessage(content=prompt)])
    return {"final_report": resp.content}


# ── Graph ─────────────────────────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(RiskState)
    g.add_node("case_finder", case_finder_node)
    g.add_node("risk_evaluator", risk_evaluator_node)

    g.set_entry_point("case_finder")
    g.add_edge("case_finder", "risk_evaluator")
    g.add_edge("risk_evaluator", END)
    return g.compile()


class RiskAgent:
    """
    법령 개정 리스크 분석

    result = agent.run(
        statute_name="법인세법",
        revision_summary="부당행위계산 부인 요건 중 시가 범위를 시가의 ±5%에서 ±3%로 강화",
        effective_date="2025-01-01"
    )
    result["final_report"]    # 리스크 보고서 (str)
    result["affected_cases"]  # 영향 받는 판례 목록
    """

    def __init__(self):
        self.graph = _build_graph()

    def run(self, statute_name: str, revision_summary: str, effective_date: str = "") -> dict:
        initial: RiskState = {
            "statute_name": statute_name,
            "revision_summary": revision_summary,
            "effective_date": effective_date or "미상",
            "affected_cases": None,
            "final_report": None,
        }
        return self.graph.invoke(initial)
