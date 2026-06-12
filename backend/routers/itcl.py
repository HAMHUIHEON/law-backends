# routers/itcl.py — 이전가격·국제조세 전문 에이전트 API
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        from agents.itcl_agent import ITCLAgent
        _agent = ITCLAgent()
    return _agent


class ITCLRequest(BaseModel):
    query: str


@router.post("/ask")
def itcl_ask(req: ITCLRequest):
    """특수관계자 거래 정보 → 정상가격 산출 방법 판단 + 리스크 평가."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query가 비어 있습니다.")
    try:
        result = _get_agent().run(query=req.query.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"에이전트 오류: {e}")
    return {
        "query": req.query,
        "final_report": result.get("final_report"),
        "court_cases": result.get("court_cases"),
        "law_articles": result.get("law_articles"),
        "itcl_issues": result.get("itcl_issues"),
    }
