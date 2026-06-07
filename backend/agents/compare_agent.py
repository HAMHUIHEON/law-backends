# agents/compare_agent.py
"""
CompareAgent — 판례 비교 에이전트

2개 이상의 판례(최대 10개)의 issue_logic_chains를 나란히 놓고
쟁점별 법원 논리 차이와 결론을 가른 사실관계 차이를 분석합니다.
"""

import json
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from langgraph.graph import END, StateGraph

from utils.cache import load_cache

_llm = ChatOpenAI(model="gpt-4.1", temperature=0)


class CompareState(TypedDict):
    case_ids: list[str]          # 2개 이상, 최대 10개

    loaded: list[dict]           # 각 판례의 분석 데이터 (못 찾은 건 {"error": ...})
    missing: list[str]

    final_report: Optional[str]


# ── 1. Loader ─────────────────────────────────────────────────────────────────

def loader_node(state: CompareState) -> dict:
    loaded = []
    missing = []

    for case_id in state["case_ids"]:
        found = None
        for stage in ["10_export_c", "09_export_b", "08_export_a",
                      "issue_logic_with_citations", "06_issue_logic"]:
            data = load_cache(case_id, stage)
            if data:
                data["_stage"] = stage
                data["_case_id"] = case_id
                found = data
                break

        if found:
            loaded.append(found)
        else:
            missing.append(case_id)

    return {"loaded": loaded, "missing": missing}


# ── 2. Comparator ─────────────────────────────────────────────────────────────

def comparator_node(state: CompareState) -> dict:
    loaded = state.get("loaded") or []
    missing = state.get("missing") or []

    if not loaded:
        return {
            "final_report": (
                f"분석 데이터를 찾을 수 없습니다: {', '.join(state['case_ids'])}\n"
                "analyze_case tool로 먼저 분석을 실행하세요."
            )
        }

    # 찾지 못한 판례 알림 포함
    missing_note = ""
    if missing:
        missing_note = f"\n⚠️ 캐시 없음 (분석 필요): {', '.join(missing)}\n\n"

    n = len(loaded)
    cases_str = json.dumps(loaded, ensure_ascii=False, indent=2)

    if n == 2:
        structure = (
            "## 기본 정보 비교\n"
            "| 항목 | 판례 A | 판례 B |\n"
            "|------|--------|--------|\n"
            "| 판례번호 | | |\n"
            "| 법원 | | |\n"
            "| 결론 | | |\n\n"
            "## 공통 쟁점 비교\n"
            "공통으로 다룬 쟁점에 대해 두 판례의 법리·적용·결론 차이를 서술\n\n"
            "## 결론을 가른 핵심 차이\n"
            "어떤 사실관계·법리 차이가 서로 다른 판결을 낳았는가\n\n"
            "## 실무 시사점\n"
            "두 판례를 함께 읽었을 때 전략적 교훈"
        )
    else:
        structure = (
            f"## 기본 정보 비교 ({n}건)\n"
            "각 판례의 법원·결론을 표로 정리\n\n"
            "## 공통 쟁점 분석\n"
            "여러 판례에서 반복되는 쟁점과 법원의 판단 경향 서술\n\n"
            "## 판례별 특이점\n"
            "각 판례가 다른 판례와 구별되는 사실관계 또는 법리\n\n"
            "## 결론 패턴 (납세자 승/패 분류)\n"
            "어떤 조건에서 납세자가 승소/패소했는가\n\n"
            "## 실무 시사점\n"
            f"{n}건 판례를 종합했을 때 전략적 교훈"
        )

    prompt = (
        "당신은 국세청 경력의 조세전문가다. 아래 판례들을 구조적으로 비교 분석하라.\n\n"
        f"{missing_note}"
        f"[판례 데이터 ({n}건)]\n{cases_str}\n\n"
        f"다음 구조로 비교 보고서를 작성하라:\n\n{structure}"
    )

    resp = _llm.invoke([HumanMessage(content=prompt)])
    report = missing_note + resp.content if missing_note else resp.content
    return {"final_report": report}


# ── Graph ─────────────────────────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(CompareState)
    g.add_node("loader", loader_node)
    g.add_node("comparator", comparator_node)

    g.set_entry_point("loader")
    g.add_edge("loader", "comparator")
    g.add_edge("comparator", END)
    return g.compile()


class CompareAgent:
    """
    2개 이상 판례 비교 분석 (최대 10개 권장)

    result = agent.run(case_ids=["2022구합7106", "2009두23945", "2015두1243"])
    result["final_report"]  # 비교 보고서 (str)
    result["missing"]       # 캐시 없는 판례 목록
    """

    def __init__(self):
        self.graph = _build_graph()

    def run(self, case_ids: list[str]) -> dict:
        if len(case_ids) < 2:
            return {"final_report": "비교할 판례를 2개 이상 입력하세요.", "missing": []}
        initial: CompareState = {
            "case_ids": case_ids[:10],  # 최대 10개
            "loaded": [],
            "missing": [],
            "final_report": None,
        }
        return self.graph.invoke(initial)
