# backend/routers/publications_a.py
from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
import json
from typing import Optional, List, Dict, Any
from fastapi.responses import FileResponse

router = APIRouter()


# ============================================================
# helpers
# ============================================================

CACHE_ROOT = Path("cache")
SOURCE = Path("cache/source")

def final_path(book_id: str, suffix: str) -> Path:
    return CACHE_ROOT / book_id / "final" / f"{book_id}.{suffix}"

def stepK_path(book_id: str, suffix: str) -> Path:
    return CACHE_ROOT / book_id / "stepK" / f"{suffix}"

def stepL_path(book_id: str, suffix: str) -> Path:
    return CACHE_ROOT / book_id / "stepL" / f"{suffix}"

def source_image_path(book_id: str, page: int) -> Path:
    return CACHE_ROOT / book_id / "ocr_images" / f"page_{page:03d}.png"

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

# ============================================================
# 0. HEAD- Strategy Reading Guide   (최고결정자용)
# ============================================================
@router.get("/{book_id}/head-reading-guide")
def get_strategy_guide(book_id: str):
    """
    최종 Executive Digest (Step 7)
    """
    path = stepL_path(book_id, "stepL_strategic_reading_guide.json")
    return load_json(path)



# ============================================================
# 0. HEAD- Final Overview  (최고결정자용)
# ============================================================
@router.get("/{book_id}/head-overview")
def get_final_overview(book_id: str):
    """
    최종 Executive Digest (Step 6)
    """
    path = stepK_path(book_id, "final_overview.json")
    return load_json(path)


# ============================================================
# 1️⃣ Executive Digest (임원용)
# ============================================================

@router.get("/{book_id}/exec-digest")
def get_exec_digest(book_id: str):
    """
    최종 Executive Digest (Step 5)
    """
    path = stepK_path(book_id, "exec_digest.json")
    return load_json(path)


# ============================================================
# 2️⃣ Executive Summary Blocks (Step 4)
# ============================================================

@router.get("/{book_id}/exec-summary")
def get_exec_summary(book_id: str):
    """
    Executive Summary Blocks (Step 4)
    """
    path = stepK_path(book_id, "exec_summary_blocks.json")
    return load_json(path)


# ============================================================
# 3️⃣ Step2 Sections (논점별 브리프 집합)
#    source: {book_id}.step2.json
# ============================================================

@router.get("/{book_id}/section")
def get_exec_summary(book_id: str):
    """
    Executive Summary Blocks (Step 2)
    """
    path = final_path(book_id, "step2.json")
    return load_json(path)


