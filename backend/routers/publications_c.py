# 29_FINAL/backend/routers/publications_c.py
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


@router.get("/{book_id}/typology")
def get_typology(book_id: str):
    path = CACHE_ROOT / book_id / "final" / f"{book_id}.typology.json"
    if not path.exists():
        raise HTTPException(status_code=404)
    return load_json(path)
