# backend/routers/publications.py
from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
import json
from typing import Optional, List, Dict, Any
from fastapi.responses import FileResponse

router = APIRouter()

CACHE_ROOT = Path("cache")
SOURCE = Path("cache/source")

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


def stepK_path(book_id: str, suffix: str) -> Path:
    return CACHE_ROOT / book_id / "stepK" / f"{suffix}"

def source_image_path(book_id: str, page: int) -> Path:
    return CACHE_ROOT / book_id / "ocr_images" / f"page_{page:03d}.png"


#공통메타 엔드포인트
@router.get("/{book_id}/meta")
def get_publication_meta(book_id: str):
    index = load_json(Path("cache/source/index.json"))

    for item in index.get("items", []):
        if item.get("book_id") == book_id:
            return item

    raise HTTPException(status_code=404, detail="Publication not found")



#“산출물 인벤토리” 엔드포인트 
@router.get("/{book_id}/artifacts")
def list_artifacts(book_id: str):
    base = CACHE_ROOT / book_id
    final_dir = base / "final"
    d_dir = base/ "mju_mappings"

    if not base.exists():
        raise HTTPException(status_code=404, detail="Publication not found")

    artifacts = {
        "A": False,
        "B": {
            "B1": False,
            "B2": False,
            "B3": False,
        },
        "C": False,
        "D": False,
        "E": False,  # ✅ 신규 추가
    }

    # =========================
    # A: 규범 압축
    # 조건: final_overview.json 존재
    # =========================
    a_final = stepK_path(book_id, "final_overview.json")
    if a_final.exists():
        artifacts["A"] = True

    # =========================
    # B: 실행 엔진 
    # =========================
    # =========================
    # B1: 조사 흐름 (🔥 final 파일)
    # =========================
    if (final_dir / f"{book_id}.stepB1.flow.json").exists():
        artifacts["B"]["B1"] = True

    # =========================
    # B2: 조사 설계도 (폴더)
    # =========================
    if (base / "B2").exists():
        artifacts["B"]["B2"] = True

    # =========================
    # B3: 운영 적용 맵 (폴더 + 파일)
    # =========================
    if (base / "B3" / "operational_application_map.json").exists():
        artifacts["B"]["B3"] = True

    # =========================
    # C: Typology / Risk Analysis
    # 조건: typology.json 존재
    # =========================
    c_typology = final_dir / f"{book_id}.typology.json"
    if c_typology.exists():
        artifacts["C"] = True

    # =========================
    # D: TPG2022
    # =========================
    d_eval = d_dir/ "mju_type_assignments_with_block_id.json"
    if d_eval.exists():
        artifacts["D"] = True

    # =========================
    # E: Regulatory Engine (Step1 존재 여부)
    # 조건: chapter*/chapter*_step1_analysis.json 존재
    # =========================
    e_files = list(base.glob("step1/chapter*_step1_analysis.json"))
    if e_files:
        artifacts["E"] = True

    return artifacts


#원문페이지
@router.get("/{book_id}/source/page/{page}")
def get_source_page(book_id: str, page: int):
    """
    OCR 원문 이미지 단일 페이지 반환
    """
    path = (
        CACHE_ROOT
        / book_id
        / "ocr_images"
        / f"page_{page:03d}.png"
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Source page not found"
        )

    return FileResponse(
        path,
        media_type="image/png",
        filename=path.name,
    )


#간행물 목록
@router.get("")
def list_publications():
    """
    간행물 목록 (선택용)
    """
    index_path = Path("cache/source/index.json")

    if not index_path.exists():
        return {
            "count": 0,
            "items": []
        }

    data = load_json(index_path)
    items = data.get("items", [])

    return {
        "count": len(items),
        "items": items,
    }
