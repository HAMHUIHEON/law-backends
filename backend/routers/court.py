# routers/court.py — 법원 판례 에이전트 API
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    case_type: Optional[str] = ""   # "CRIMINAL" | "ADMIN" | ""
    court: Optional[str] = ""
    n_results: int = 8


class AskRequest(BaseModel):
    question: str


@router.get("/stats")
def get_stats():
    """법원 판례 DB 통계."""
    from agents.court_agent import get_court_stats
    return {"result": get_court_stats.invoke({})}


@router.post("/search")
def search(req: SearchRequest):
    """법원 판례 벡터 검색."""
    from agents.court_agent import search_court_cases
    result = search_court_cases.invoke({
        "query": req.query,
        "case_type": req.case_type or "",
        "court": req.court or "",
        "n_results": req.n_results,
    })
    return {"result": result}


@router.get("/case/{case_id:path}")
def get_case(case_id: str):
    """특정 판례 상세 조회."""
    from agents.court_agent import get_case_detail
    result = get_case_detail.invoke({"case_id": case_id})
    if "찾을 수 없습니다" in result:
        raise HTTPException(status_code=404, detail=result)
    return {"result": result}


@router.get("/trend")
def trend(case_type: str = "", year: str = ""):
    """판례 트렌드 분석."""
    from agents.court_agent import analyze_case_trend
    result = analyze_case_trend.invoke({"case_type": case_type, "year": year})
    return {"result": result}


@router.post("/similar")
def similar(req: AskRequest):
    """의뢰인 사건과 유사 판례 검색."""
    from agents.court_agent import find_similar_cases
    result = find_similar_cases.invoke({
        "fact_summary": req.question,
        "case_type": "",
        "n": 5,
    })
    return {"result": result}


@router.post("/ask")
def ask_agent(req: AskRequest):
    """법원 판례 에이전트에게 자연어 질문."""
    from agents.court_agent import CourtAgent

    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question이 비어 있습니다.")

    try:
        agent = CourtAgent()
        answer = agent.ask(req.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"에이전트 오류: {e}")

    return {"question": req.question, "answer": answer}
