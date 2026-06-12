# agents/rebuttal_agent.py
"""
RebuttalAgent — 반론 초안 생성 에이전트

과세처분 이유서를 입력하면 납세자 승소 판례·재결례에서 반론 논거를 추출해
이의신청서·심판청구서 초안을 생성합니다.

데이터 소스:
  - Chroma taxlaw_prec: 법원 판례 32,628건 (납세자 승소 필터)
  - Chroma taxtr_cases: 조세심판 재결례 2,463건 (인용 필터)
  - Chroma law_articles: 세법 조문 6,687건

LangGraph: ClaimExtractor → CaseSearcher → DraftWriter → Reflector
"""

import json
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage
from utils.llm import get_llm, DEFAULT_MODEL
from langgraph.graph import END, StateGraph

_llm = None
_MAX_REFLECT = 1


def _get_llm():
    global _llm
    if _llm is None:
        _llm = get_llm(model=DEFAULT_MODEL, temperature=0)
    return _llm


class RebuttalState(TypedDict):
    disposition_text: str

    tax_claims: list
    key_issues: list

    winning_court_cases: Optional[list]
    favorable_taxtr_cases: Optional[list]
    law_articles: Optional[list]

    draft: Optional[str]
    reflect_count: int
    final_report: Optional[str]


# ── 1. ClaimExtractor ─────────────────────────────────────────────────────────

def claim_extractor_node(state: RebuttalState) -> dict:
    prompt = (
        "당신은 조세 전문 변호사다. 아래 과세처분 이유서에서 과세관청의 주장을 분석하라.\n\n"
        f"[과세처분 이유서]\n{state['disposition_text']}\n\n"
        "반환 형식 (JSON만):\n"
        '{"tax_claims": ["과세관청 주장 1", "주장 2"], '
        '"key_issues": ["반론해야 할 핵심 쟁점 1", "쟁점 2"]}'
    )
    resp = _get_llm().invoke([HumanMessage(content=prompt)])
    try:
        data = json.loads(resp.content.strip().removeprefix("```json").removesuffix("```").strip())
    except Exception:
        data = {
            "tax_claims": [state["disposition_text"][:200]],
            "key_issues": [state["disposition_text"][:200]],
        }
    return {
        "tax_claims": data.get("tax_claims") or [],
        "key_issues": data.get("key_issues") or [],
    }


# ── 2. CaseSearcher ───────────────────────────────────────────────────────────

def case_searcher_node(state: RebuttalState) -> dict:
    from db.chroma_search import search_taxlaw_prec, search_taxtr_cases, search_law_articles

    combined = " ".join(state["key_issues"])

    winning_court = search_taxlaw_prec(combined, n=8, filter_winning=True)
    # 필터 후 결과 부족하면 전체로 fallback
    if len(winning_court) < 3:
        winning_court = search_taxlaw_prec(combined, n=8)

    favorable_taxtr = search_taxtr_cases(combined, n=5, filter_favorable=True)
    if len(favorable_taxtr) < 2:
        favorable_taxtr = search_taxtr_cases(combined, n=5)

    law_articles = search_law_articles(combined, n=4)

    return {
        "winning_court_cases": winning_court,
        "favorable_taxtr_cases": favorable_taxtr,
        "law_articles": law_articles,
    }


# ── 3. DraftWriter ────────────────────────────────────────────────────────────

def draft_writer_node(state: RebuttalState) -> dict:
    court_str = json.dumps(state.get("winning_court_cases") or [], ensure_ascii=False, indent=2)
    taxtr_str = json.dumps(state.get("favorable_taxtr_cases") or [], ensure_ascii=False, indent=2)
    law_str = json.dumps(state.get("law_articles") or [], ensure_ascii=False, indent=2)
    claims_str = "\n".join(f"- {c}" for c in state.get("tax_claims") or [])
    issues_str = "\n".join(f"- {i}" for i in state.get("key_issues") or [])

    prompt = (
        "당신은 조세심판원 심판관 경력의 조세전문 변호사다.\n"
        "아래 정보를 바탕으로 이의신청서 또는 심판청구서 반론 초안을 작성하라.\n\n"
        f"[과세관청 주요 주장]\n{claims_str}\n\n"
        f"[반론해야 할 핵심 쟁점]\n{issues_str}\n\n"
        f"[참고 법원 판례 (납세자 승소 중심)]\n{court_str}\n\n"
        f"[참고 조세심판 재결례 (인용 중심)]\n{taxtr_str}\n\n"
        f"[관련 세법 조문]\n{law_str}\n\n"
        "다음 구조로 반론 초안을 작성하라:\n\n"
        "## 처분의 위법성 개요\n\n"
        "## 쟁점별 반론\n"
        "각 쟁점:\n"
        "  - 과세관청 주장 요약\n"
        "  - 납세자 반론 (판례·재결례·조문 근거 포함)\n\n"
        "## 관련 판례 및 재결례 요지\n\n"
        "## 관련 법령 근거\n\n"
        "## 결론 및 청구취지\n\n"
        "※ 법적 근거와 판례·재결 번호를 구체적으로 명시할 것"
    )

    resp = _get_llm().invoke([HumanMessage(content=prompt)])
    return {"draft": resp.content}


# ── 4. Reflector ──────────────────────────────────────────────────────────────

def reflector_node(state: RebuttalState) -> dict:
    prompt = (
        "당신은 조세심판원 심판관이다. 아래 반론 초안을 검토하고 평가하라.\n\n"
        f"[반론 초안]\n{state['draft']}\n\n"
        "평가 기준 (각 항목 1~5점):\n"
        "1. 과세관청 주장을 정확히 반박하는가\n"
        "2. 판례·재결례 인용이 구체적이고 적절한가\n"
        "3. 법적 논거가 충분한가\n"
        "4. 구성이 논리적인가\n\n"
        "반환 형식 (JSON만):\n"
        '{"score": 총점(4~20), "verdict": "pass" 또는 "revise", '
        '"feedback": "개선 필요 사항 (2~3문장)"}'
    )
    resp = _get_llm().invoke([HumanMessage(content=prompt)])
    try:
        data = json.loads(resp.content.strip().removeprefix("```json").removesuffix("```").strip())
    except Exception:
        data = {"score": 15, "verdict": "pass", "feedback": ""}

    if data.get("verdict") == "pass" or state["reflect_count"] >= _MAX_REFLECT:
        return {"final_report": state["draft"], "reflect_count": state["reflect_count"]}

    refine_prompt = (
        f"아래 피드백을 반영해 반론 초안을 개선하라.\n\n"
        f"[피드백]\n{data.get('feedback', '')}\n\n"
        f"[기존 초안]\n{state['draft']}"
    )
    refined = _get_llm().invoke([HumanMessage(content=refine_prompt)])
    return {
        "draft": refined.content,
        "final_report": refined.content,
        "reflect_count": state["reflect_count"] + 1,
    }


def _route_reflector(state: RebuttalState) -> str:
    if state.get("final_report"):
        return END
    return "reflector"


# ── Graph ─────────────────────────────────────────────────────────────────────

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        g = StateGraph(RebuttalState)
        g.add_node("claim_extractor", claim_extractor_node)
        g.add_node("case_searcher", case_searcher_node)
        g.add_node("draft_writer", draft_writer_node)
        g.add_node("reflector", reflector_node)
        g.set_entry_point("claim_extractor")
        g.add_edge("claim_extractor", "case_searcher")
        g.add_edge("case_searcher", "draft_writer")
        g.add_edge("draft_writer", "reflector")
        g.add_conditional_edges("reflector", _route_reflector)
        _graph = g.compile()
    return _graph


class RebuttalAgent:
    """
    과세처분 이유서 → 반론 초안 (이의신청서/심판청구서)

    result = agent.run(disposition_text="과세처분 이유서...")
    result["final_report"]          # 최종 반론 초안 (str)
    result["winning_court_cases"]   # 참고한 납세자 승소 판례
    result["favorable_taxtr_cases"] # 참고한 인용 재결례
    result["law_articles"]          # 관련 조문
    """

    def run(self, disposition_text: str) -> dict:
        initial: RebuttalState = {
            "disposition_text": disposition_text,
            "tax_claims": [],
            "key_issues": [],
            "winning_court_cases": None,
            "favorable_taxtr_cases": None,
            "law_articles": None,
            "draft": None,
            "reflect_count": 0,
            "final_report": None,
        }
        return _get_graph().invoke(initial)
