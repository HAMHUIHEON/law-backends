# agents/strategy_agent.py
"""
StrategyAgent — 의뢰인 사건 전략 에이전트

의뢰인이 제출한 사건 요약을 받아 유사 판례를 분석하고
경정청구 / 조세심판 / 소송 중 최적 전략을 권고합니다.

데이터 소스:
  - Chroma taxlaw_prec: NTS 법원 판례 32,628건
  - Chroma taxtr_cases: 조세심판 재결례 2,463건
  - Chroma law_articles: 세법 조문 6,687건

LangGraph: FactExtractor → CaseSearcher → Strategist
"""

import json
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage
from utils.llm import get_llm, DEFAULT_MODEL
from langgraph.graph import END, StateGraph

_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = get_llm(model=DEFAULT_MODEL, temperature=0)
    return _llm


class StrategyState(TypedDict):
    client_summary: str

    key_facts: str
    legal_issues: list
    tax_type: str

    court_cases: Optional[list]
    taxtr_cases: Optional[list]
    law_articles: Optional[list]

    final_report: Optional[str]


# ── 1. FactExtractor ──────────────────────────────────────────────────────────

def fact_extractor_node(state: StrategyState) -> dict:
    prompt = (
        "당신은 세무·법률 전문가다. 아래 의뢰인 사건 요약을 분석해 JSON으로만 반환하라.\n\n"
        f"사건 요약:\n{state['client_summary']}\n\n"
        "반환 형식 (JSON만, 다른 텍스트 없음):\n"
        '{"key_facts": "핵심 사실관계 요약 (3~5문장)", '
        '"legal_issues": ["쟁점 1", "쟁점 2"], '
        '"tax_type": "세목 (예: 법인세, 소득세, 부가가치세, 국제조세, 상속세)"}'
    )
    resp = _get_llm().invoke([HumanMessage(content=prompt)])
    try:
        data = json.loads(resp.content.strip().removeprefix("```json").removesuffix("```").strip())
    except Exception:
        data = {
            "key_facts": state["client_summary"],
            "legal_issues": [state["client_summary"][:100]],
            "tax_type": "미분류",
        }
    return {
        "key_facts": data.get("key_facts", ""),
        "legal_issues": data.get("legal_issues") or [state["client_summary"][:100]],
        "tax_type": data.get("tax_type", "미분류"),
    }


# ── 2. CaseSearcher ───────────────────────────────────────────────────────────

def case_searcher_node(state: StrategyState) -> dict:
    from db.chroma_search import search_taxlaw_prec, search_taxtr_cases, search_law_articles

    combined_query = " ".join(state["legal_issues"]) + " " + state.get("tax_type", "")

    court_cases = search_taxlaw_prec(combined_query, n=8)
    taxtr_cases = search_taxtr_cases(combined_query, n=5)
    law_articles = search_law_articles(combined_query, n=4)

    return {
        "court_cases": court_cases,
        "taxtr_cases": taxtr_cases,
        "law_articles": law_articles,
    }


# ── 3. Strategist ─────────────────────────────────────────────────────────────

def strategist_node(state: StrategyState) -> dict:
    court_str = json.dumps(state.get("court_cases") or [], ensure_ascii=False, indent=2)
    taxtr_str = json.dumps(state.get("taxtr_cases") or [], ensure_ascii=False, indent=2)
    law_str = json.dumps(state.get("law_articles") or [], ensure_ascii=False, indent=2)

    prompt = (
        "당신은 국세청 경력 10년의 세무사 겸 조세전문 변호사다.\n"
        "아래 의뢰인 사건과 판례·재결례·조문 분석 결과를 바탕으로 전략 보고서를 작성하라.\n\n"
        f"[의뢰인 사건 요약]\n{state['client_summary']}\n\n"
        f"[핵심 사실관계]\n{state['key_facts']}\n\n"
        f"[주요 쟁점]\n" + "\n".join(f"- {i}" for i in state["legal_issues"]) + "\n\n"
        f"[유사 법원 판례]\n{court_str}\n\n"
        f"[유사 조세심판 재결례]\n{taxtr_str}\n\n"
        f"[관련 세법 조문]\n{law_str}\n\n"
        "다음 구조로 보고서를 작성하라:\n\n"
        "## 사건 개요\n\n"
        "## 핵심 쟁점\n\n"
        "## 유사 판례 및 재결례 분석\n"
        "  - 판례번호/재결번호, 결론, 이 사건과의 유사점·차이점\n\n"
        "## 전략 권고\n"
        "  ### 경정청구 (가능 여부, 기한, 승산)\n"
        "  ### 조세심판청구 (강·약점, 재결 경향)\n"
        "  ### 행정소송 (강·약점)\n"
        "  ### 최종 권고: 어떤 경로를 먼저 선택해야 하는가\n\n"
        "## 관련 법령 근거\n\n"
        "## 리스크 포인트\n\n"
        "## 즉시 준비해야 할 증거·서류"
    )

    resp = _get_llm().invoke([HumanMessage(content=prompt)])
    return {"final_report": resp.content}


# ── Graph ─────────────────────────────────────────────────────────────────────

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        g = StateGraph(StrategyState)
        g.add_node("fact_extractor", fact_extractor_node)
        g.add_node("case_searcher", case_searcher_node)
        g.add_node("strategist", strategist_node)
        g.set_entry_point("fact_extractor")
        g.add_edge("fact_extractor", "case_searcher")
        g.add_edge("case_searcher", "strategist")
        g.add_edge("strategist", END)
        _graph = g.compile()
    return _graph


class StrategyAgent:
    """
    의뢰인 사건 요약 → 유사 판례 검색 → 전략 권고 (경정청구/심판/소송)

    result = agent.run(client_summary="...")
    result["final_report"]   # 전략 보고서 (str)
    result["court_cases"]    # 유사 법원 판례 목록
    result["taxtr_cases"]    # 유사 재결례 목록
    result["law_articles"]   # 관련 조문
    """

    def run(self, client_summary: str) -> dict:
        initial: StrategyState = {
            "client_summary": client_summary,
            "key_facts": "",
            "legal_issues": [],
            "tax_type": "",
            "court_cases": None,
            "taxtr_cases": None,
            "law_articles": None,
            "final_report": None,
        }
        return _get_graph().invoke(initial)
