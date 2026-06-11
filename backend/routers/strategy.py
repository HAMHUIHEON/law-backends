# routers/strategy.py — 의뢰인 사건 전략 + 반론 초안 에이전트 API
import sys
from pathlib import Path
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class CaseRequest(BaseModel):
    summary: str        # 의뢰인 사건 요약


class RebuttalRequest(BaseModel):
    disposition_text: str   # 과세처분 이유서


@router.post("/strategy")
def analyze_strategy(req: CaseRequest):
    """의뢰인 사건 → 유사 판례 검색 + 전략 보고서."""
    if not req.summary.strip():
        raise HTTPException(400, "summary가 비어 있습니다.")
    from agents.strategy_agent import StrategyAgent
    result = StrategyAgent().run(req.summary)
    return result


@router.post("/rebuttal")
def generate_rebuttal(req: RebuttalRequest):
    """과세처분 이유서 → 납세자 승소 판례 검색 + 반론 초안."""
    if not req.disposition_text.strip():
        raise HTTPException(400, "disposition_text가 비어 있습니다.")
    from agents.rebuttal_agent import RebuttalAgent
    result = RebuttalAgent().run(req.disposition_text)
    return result
