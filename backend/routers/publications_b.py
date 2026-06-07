# backend/routers/publications_b.py
from fastapi import APIRouter, HTTPException
from pathlib import Path
import json
from typing import Dict, Any, List

router = APIRouter()

CACHE_ROOT = Path("cache")


# ============================================================
# helpers
# ============================================================

def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {path}"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid JSON format: {path}"
        )


def book_base(book_id: str) -> Path:
    return CACHE_ROOT / book_id


# ============================================================
# B1 — Operational Flow Segmentation
# ============================================================

@router.get("/{book_id}/flow")
def get_b1_flow(book_id: str):
    """
    B1 결과:
    - 조사/집행 흐름 단위 segmentation
    """
    base = book_base(book_id)
    path = base / "final" / f"{book_id}.stepB1.flow.json"

    return load_json(path)


# ============================================================
# B2 — Block-level Investigation Blueprints
# ============================================================

@router.get("/{book_id}/blueprints")
def get_b2_blueprints(book_id: str):
    """
    B2 결과:
    - 블록별 조사 설계 청사진
    - 여러 파일을 하나의 리스트로 반환
    """
    base = book_base(book_id)
    b2_dir = base / "B2"

    if not b2_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="B2 outputs not found"
        )

    results: List[Dict[str, Any]] = []

    for p in sorted(b2_dir.glob("*.json")):
        try:
            results.append(
                json.loads(p.read_text(encoding="utf-8"))
            )
        except Exception:
            continue

    if not results:
        raise HTTPException(
            status_code=404,
            detail="No valid B2 blueprints found"
        )

    return {
        "book_id": book_id,
        "count": len(results),
        "items": results,
    }


# ============================================================
# B3 — Operational Application Map (최종 산출물)
# ============================================================

@router.get("/{book_id}/operational-map")
def get_b3_operational_map(book_id: str):
    """
    B3 결과:
    - 현업 적용용 조사/집행 매핑 맵
    """
    base = book_base(book_id)
    path = base / "B3" / "operational_application_map.json"

    return load_json(path)
