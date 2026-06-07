# 29_FINAL/backend/routers/publications_e.py

from fastapi import APIRouter, HTTPException
from pathlib import Path
import json
from typing import Dict, Any, List, Optional

router = APIRouter()

CACHE_ROOT = Path("cache")

CHAPTER_KO_MAP = {
    "chapter1": "제1장",
    "chapter2": "제2장",
    "chapter3": "제3장",
}


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


def require_book(book_id: str) -> Path:
    base = book_base(book_id)
    if not base.exists():
        raise HTTPException(status_code=404, detail="Publication not found")
    return base


def parse_section_title_from_slug(slug: str) -> str:
    """
    slug 예:
      '제1장_제2절_세무조사의_관할'
    반환:
      '제2절 세무조사의 관할'
    """
    parts = slug.split("_")
    if len(parts) < 2:
        return slug.replace("_", " ")
    # parts[0] = 제1장, parts[1] = 제2절
    section = parts[1]
    rest = " ".join(parts[2:]).replace("_", " ").strip()
    if rest:
        return f"{section} {rest}"
    return section


# ============================================================
# E - STEP1 (✅ 스샷 기준: cache/{book_id}/step1/*)
# ============================================================

@router.get("/{book_id}/E/{chapter}/step1")
def get_e_step1(book_id: str, chapter: str):
    """
    예:
      /{book_id}/E/chapter1/step1
    실제 파일:
      cache/{book_id}/step1/chapter1_step1_analysis.json
    """
    base = require_book(book_id)

    if chapter not in CHAPTER_KO_MAP:
        raise HTTPException(status_code=400, detail="Invalid chapter (use chapter1|chapter2|chapter3)")

    path = base / "step1" / f"{chapter}_step1_analysis.json"
    return load_json(path)


# ============================================================
# E - STEP2 (절 목록) ✅ step2 폴더 한 곳에 절 파일들 모여있음
# ============================================================

@router.get("/{book_id}/E/{chapter}/step2/sections")
def list_e_step2_sections(book_id: str, chapter: str):
    """
    예:
      /{book_id}/E/chapter1/step2/sections
    실제 파일들:
      cache/{book_id}/step2/제1장_제1절_통칙.json
      cache/{book_id}/step2/제1장_제2절_....json
    반환은 목록만 (드롭다운 용)
    """
    base = require_book(book_id)

    if chapter not in CHAPTER_KO_MAP:
        raise HTTPException(status_code=400, detail="Invalid chapter (use chapter1|chapter2|chapter3)")

    step2_dir = base / "step2"
    if not step2_dir.exists():
        raise HTTPException(status_code=404, detail="Step2 folder not found")

    chapter_ko = CHAPTER_KO_MAP[chapter]
    files = sorted(step2_dir.glob(f"{chapter_ko}_*.json"))

    if not files:
        raise HTTPException(status_code=404, detail="No section files found for this chapter")

    sections: List[Dict[str, str]] = []
    for f in files:
        slug = f.stem  # 확장자 제거
        sections.append({
            "slug": slug,
            "title": parse_section_title_from_slug(slug),
        })

    return {
        "chapter": chapter,
        "chapter_ko": chapter_ko,
        "sections": sections,
    }


# ============================================================
# E - STEP2 (절 단건) ✅ 클릭하면 이걸로 본문 로딩
# ============================================================

@router.get("/{book_id}/E/{chapter}/step2/sections/{section_slug}")
def get_e_step2_section(book_id: str, chapter: str, section_slug: str):
    """
    예:
      /{book_id}/E/chapter1/step2/sections/제1장_제2절_세무조사의_관할
    실제 파일:
      cache/{book_id}/step2/{section_slug}.json
    """
    base = require_book(book_id)

    if chapter not in CHAPTER_KO_MAP:
        raise HTTPException(status_code=400, detail="Invalid chapter (use chapter1|chapter2|chapter3)")

    chapter_ko = CHAPTER_KO_MAP[chapter]
    if not section_slug.startswith(f"{chapter_ko}_"):
        raise HTTPException(status_code=400, detail="section_slug does not match chapter")

    path = base / "step2" / f"{section_slug}.json"
    return load_json(path)


# ============================================================
# (옵션) E - STEP2 통합본 (chapter 폴더 안 통합 JSON)
# ============================================================

@router.get("/{book_id}/E/{chapter}/step2/combined")
def get_e_step2_combined(book_id: str, chapter: str):
    """
    예:
      /{book_id}/E/chapter1/step2/combined
    실제 파일:
      cache/{book_id}/chapter1/chapter1_step2_sectional_analysis.json
    """
    base = require_book(book_id)

    if chapter not in CHAPTER_KO_MAP:
        raise HTTPException(status_code=400, detail="Invalid chapter (use chapter1|chapter2|chapter3)")

    path = base / chapter / f"{chapter}_step2_sectional_analysis.json"
    return load_json(path)

# ============================================================
# E - STEP2B (정적 분석)
# ============================================================

@router.get("/{book_id}/E/{chapter}/step2b")
def get_e_step2b(book_id: str, chapter: str):
    """
    예:
      /{book_id}/E/chapter1/step2b

    실제 파일:
      cache/{book_id}/step2b/chapter1_step2b_analysis.json
    """

    base = require_book(book_id)

    if chapter not in CHAPTER_KO_MAP:
        raise HTTPException(
            status_code=400,
            detail="Invalid chapter (use chapter1|chapter2|chapter3)"
        )

    path = base / "step2b" / f"{chapter}_step2b_analysis.json"

    return load_json(path)
