# routers/strategy.py — 불복전략 + 반론초안 + 법령개정리스크 API
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

_strategy_agent = None
_rebuttal_agent = None
_risk_agent = None


def _get_strategy():
    global _strategy_agent
    if _strategy_agent is None:
        from agents.strategy_agent import StrategyAgent
        _strategy_agent = StrategyAgent()
    return _strategy_agent


def _get_rebuttal():
    global _rebuttal_agent
    if _rebuttal_agent is None:
        from agents.rebuttal_agent import RebuttalAgent
        _rebuttal_agent = RebuttalAgent()
    return _rebuttal_agent


def _get_risk():
    global _risk_agent
    if _risk_agent is None:
        from agents.risk_agent import RiskAgent
        _risk_agent = RiskAgent()
    return _risk_agent


class CaseRequest(BaseModel):
    summary: str


class RebuttalRequest(BaseModel):
    disposition_text: str


class RiskRequest(BaseModel):
    statute_name: str
    revision_summary: str
    effective_date: Optional[str] = ""


@router.post("/strategy")
def analyze_strategy(req: CaseRequest):
    """의뢰인 사건 요약 → 유사 판례 검색 + 불복전략 보고서."""
    if not req.summary.strip():
        raise HTTPException(status_code=400, detail="summary가 비어 있습니다.")
    try:
        result = _get_strategy().run(client_summary=req.summary.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"에이전트 오류: {e}")
    return {
        "final_report": result.get("final_report"),
        "court_cases": result.get("court_cases"),
        "taxtr_cases": result.get("taxtr_cases"),
        "law_articles": result.get("law_articles"),
    }


@router.post("/rebuttal")
def generate_rebuttal(req: RebuttalRequest):
    """과세처분 이유서 → 납세자 승소 판례 검색 + 반론 초안."""
    if not req.disposition_text.strip():
        raise HTTPException(status_code=400, detail="disposition_text가 비어 있습니다.")
    try:
        result = _get_rebuttal().run(disposition_text=req.disposition_text.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"에이전트 오류: {e}")
    return {
        "final_report": result.get("final_report"),
        "winning_court_cases": result.get("winning_court_cases"),
        "favorable_taxtr_cases": result.get("favorable_taxtr_cases"),
        "law_articles": result.get("law_articles"),
    }


@router.post("/risk")
def analyze_law_risk(req: RiskRequest):
    """법령 개정 내용 → 기존 판례·재결례 영향 리스크 분석."""
    if not req.statute_name.strip():
        raise HTTPException(status_code=400, detail="statute_name이 비어 있습니다.")
    try:
        result = _get_risk().run(
            statute_name=req.statute_name.strip(),
            revision_summary=req.revision_summary.strip(),
            effective_date=req.effective_date or "",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"에이전트 오류: {e}")
    return {
        "final_report": result.get("final_report"),
        "affected_court_cases": result.get("affected_court_cases"),
        "affected_taxtr_cases": result.get("affected_taxtr_cases"),
        "revised_articles": result.get("revised_articles"),
    }
