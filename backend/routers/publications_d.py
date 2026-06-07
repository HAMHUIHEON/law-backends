# 29_FINAL/backend/routers/publications_d.py
from fastapi import APIRouter, HTTPException
from pathlib import Path
import json
from typing import Dict, Any, List

router = APIRouter()

# ============================================================
# helpers
# ============================================================

CACHE_ROOT = Path("cache")


def stepD_path(book_id: str) -> Path:
    return CACHE_ROOT / book_id / "judgement_units_with_block_id"


def stepM_path(book_id: str, suffix: str) -> Path:
    return CACHE_ROOT / book_id / "mju_mappings" / f"{suffix}"


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


def load_all_judgement_units_sorted(book_id: str) -> List[Dict[str, Any]]:
    """
    cache/{book_id}/judgement_units_with_block_id/*.json
    을 모두 읽어서 block_id 순서대로 정렬한 리스트를 반환.
    """
    dir_path = stepD_path(book_id)

    if not dir_path.exists() or not dir_path.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Directory not found: {dir_path}"
        )

    units: List[Dict[str, Any]] = []

    for fp in sorted(dir_path.glob("*.json")):
        try:
            doc = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid JSON format: {fp}"
            )
        units.append(doc)

    def sort_key(doc: Dict[str, Any]) -> str:
        block_id = doc.get("block_id")
        if isinstance(block_id, str) and block_id.strip():
            return block_id.strip()
        return ""

    units.sort(key=sort_key)
    return units


# ============================================================
# 0. mju
# ============================================================

@router.get("/{book_id}/mju_list")
def get_mju_list(book_id: str):
    """
    mju
    """
    path = stepM_path(book_id, "mju_type_assignments_with_block_id.json")
    return load_json(path)


# ============================================================
# 1. ju blocks (merged, sorted by block_id)
# ============================================================

@router.get("/{book_id}/mju_blocks")
def get_ju_blocks(book_id: str):
    """
    통합된 judgement_units (block_id 순서 정렬)
    """
    units = load_all_judgement_units_sorted(book_id)
    return {
        "book_id": book_id,
        "judgement_units": units,
    }
