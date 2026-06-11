# routers/risk.py — 법령 개정 리스크 + 컨설팅 인사이트 API
import sys
import os
from pathlib import Path

# RISK 모듈 import를 위해 프로젝트 루트를 path에 추가
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Literal

router = APIRouter()


# ── 요청/응답 모델 ───────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    law_name: str
    kind: Literal["LAW", "DECREE", "RULE"] = "LAW"
    version_key: Optional[str] = None  # None이면 최신 버전 자동 선택


class AskRequest(BaseModel):
    question: str


# ── 지원 법령 목록 ────────────────────────────────────────────────────────────

@router.get("/laws")
def list_laws():
    """지원하는 세법 목록과 보유 버전 수를 반환합니다."""
    from RISK.consulting import LAW_SLUGS, KIND_FOLDER, LAW_DIR

    result = []
    for law_name, slug in LAW_SLUGS.items():
        kinds = []
        for kind, folder in KIND_FOLDER.items():
            import json
            idx_path = LAW_DIR / slug / folder / "_version_index.json"
            if idx_path.exists():
                with idx_path.open(encoding="utf-8") as f:
                    cnt = len(json.load(f))
                kinds.append({"kind": kind, "version_count": cnt})
        result.append({"law_name": law_name, "slug": slug, "kinds": kinds})

    return {"laws": result}


# ── 버전 목록 ────────────────────────────────────────────────────────────────

@router.get("/{law_name}/{kind}/versions")
def get_versions(law_name: str, kind: str):
    """특정 법령의 보유 버전 목록을 최신순으로 반환합니다."""
    from RISK.consulting import list_version_keys

    try:
        versions = list_version_keys(law_name, kind)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"law_name": law_name, "kind": kind, "versions": versions}


# ── 최신 버전 컨설팅 인사이트 (캐시 우선) ──────────────────────────────────────

@router.get("/{law_name}/{kind}/latest")
def get_latest_consulting(law_name: str, kind: str):
    """
    법령 최신 버전 컨설팅 인사이트를 반환합니다.
    캐시가 있으면 즉시 반환, 없으면 분석을 실행합니다.
    """
    from RISK.consulting import run_full_analysis

    try:
        result = run_full_analysis(law_name, kind)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 오류: {e}")

    return result.to_dict()


# ── 특정 버전 분석 실행 ──────────────────────────────────────────────────────

@router.post("/analyze")
def analyze_version(req: AnalyzeRequest):
    """
    법령 특정 버전에 대해 개정 관측 + 컨설팅 인사이트를 실행합니다.
    캐시가 있으면 재실행 없이 캐시를 반환합니다.
    """
    from RISK.consulting import run_full_analysis

    try:
        result = run_full_analysis(req.law_name, req.kind, req.version_key)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 오류: {e}")

    return result.to_dict()


# ── 에이전트 질의 ────────────────────────────────────────────────────────────

@router.post("/ask")
def ask_agent(req: AskRequest):
    """
    법령 개정 리스크 에이전트에게 자연어로 질문합니다.

    예시 질문:
    - "법인세법이 최근에 어떻게 바뀌었나요?"
    - "소득세법 개정으로 경정청구 기회가 있나요?"
    - "국세기본법 최신 개정의 컨설팅 포인트를 알려주세요"
    """
    from RISK.agent import RiskAgent

    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question이 비어 있습니다.")

    try:
        agent = RiskAgent()
        answer = agent.ask(req.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"에이전트 오류: {e}")

    return {"question": req.question, "answer": answer}


# ── 외부 법령 → 세법 연동 영향 분석 ─────────────────────────────────────────

@router.get("/cross-law/{source_law}")
def get_cross_law_impact(source_law: str):
    """
    외부 참조 법령(조세특례제한법, 상속세법 등) 최신 개정이
    연동 세법에 미치는 영향을 분석합니다.
    """
    from RISK.consulting import run_cross_law_analysis, CROSS_LAW_LINKS

    if source_law not in CROSS_LAW_LINKS:
        raise HTTPException(
            status_code=404,
            detail=f"'{source_law}'은 cross-law 분석 대상이 아닙니다. 지원: {list(CROSS_LAW_LINKS.keys())}",
        )

    try:
        out = run_cross_law_analysis(source_law)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 오류: {e}")

    if not out:
        raise HTTPException(status_code=404, detail="분석 결과 없음")

    return out.model_dump()


# ── 전체 외부 법령 연동 현황 ──────────────────────────────────────────────────

@router.get("/cross-law")
def list_cross_law_links():
    """외부 참조 법령과 연동 세법 관계 목록을 반환합니다."""
    from RISK.consulting import CROSS_LAW_LINKS
    return {"links": {k: v for k, v in CROSS_LAW_LINKS.items()}}


# ── 새 버전 감지 (백그라운드) ─────────────────────────────────────────────────

_monitor_status: dict = {"running": False, "last_result": None}


def _run_monitor_bg():
    _monitor_status["running"] = True
    try:
        from RISK.monitor import poll_all_laws
        result = poll_all_laws(kinds=["LAW"])
        _monitor_status["last_result"] = {
            "new_versions": {k: v for k, v in result.items()},
            "total_new": sum(len(v) for v in result.values()),
        }
    except Exception as e:
        _monitor_status["last_result"] = {"error": str(e)}
    finally:
        _monitor_status["running"] = False


@router.post("/monitor")
def trigger_monitor(background_tasks: BackgroundTasks):
    """
    법제처 DRF API와 비교해 새로 공포된 법령 버전을 감지합니다.
    백그라운드에서 실행되며, GET /api/risk/monitor/status로 결과를 확인합니다.
    """
    if _monitor_status["running"]:
        return {"status": "이미 실행 중입니다."}
    background_tasks.add_task(_run_monitor_bg)
    return {"status": "감지 시작됨"}


@router.get("/monitor/status")
def get_monitor_status():
    """새 버전 감지 상태 및 결과를 반환합니다."""
    return _monitor_status
