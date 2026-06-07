# 29_FINAL/backend/routers/cases.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from pathlib import Path
import json
import re
from fastapi import HTTPException
from services.pipeline import (run_case_pipeline, normalize_case_id, 
                               get_current_user_id, get_monthly_case_usage_detail)


router = APIRouter()


@router.post("/upload-and-run")
async def upload_and_run_case(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)

    content = await file.read()
    pdf_path = upload_dir / file.filename
    pdf_path.write_bytes(content)

    case_id = normalize_case_id(pdf_path.stem)

    pdf_path = upload_dir / f"{case_id}.pdf"
    pdf_path.write_bytes(content)

    return run_case_pipeline(case_id, pdf_path, user_id)



from fastapi import Depends, HTTPException
from services.pipeline import get_current_user_id


@router.get("/{case_id}/report-a")
def get_report_a(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from utils.cache import load_cache

    data = load_cache(case_id, "export_A_full.json")
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"export_A_full.json not found for case_id={case_id}",
        )
    return data


@router.get("/{case_id}/report-b")
def get_report_b(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from utils.cache import load_cache

    data = load_cache(case_id, "export_B_full.json")
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"export_B_full.json not found for case_id={case_id}",
        )
    return data


@router.get("/{case_id}/report-c")
def get_report_c(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from utils.cache import load_cache

    data = load_cache(case_id, "export_C_full.json")
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"export_C_full.json not found for case_id={case_id}",
        )
    return data



@router.get("/me/case-usage")
def get_my_case_usage(
    user_id: str = Depends(get_current_user_id),
):
    return get_monthly_case_usage_detail(user_id)


