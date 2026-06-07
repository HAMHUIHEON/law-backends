from pathlib import Path
from typing import Optional
from fastapi import HTTPException

CACHE_ROOT = Path("cache")


def _normalize_case_id(case_id: str) -> str:
    s = (case_id or "").strip()
    if "_" in s:
        return s.split("_")[-1].strip()
    return s


def find_case_dir_by_suffix(case_id: str) -> Optional[Path]:
    if not CACHE_ROOT.exists():
        return None

    suffix = f"_{case_id}"

    matches = [
        d for d in CACHE_ROOT.iterdir()
        if d.is_dir() and d.name.endswith(suffix)
    ]

    if not matches:
        return None

    if len(matches) == 1:
        return matches[0]

    # ⚠️ 중복 발견 → 설계상 에러
    raise RuntimeError(
        f"Multiple case dirs found for case_id={case_id}: "
        f"{[d.name for d in matches]}"
    )


def resolve_report_json_path(case_id: str, filename: str) -> Path:
    # 1️⃣ 정확히 suffix로 매칭되는 케이스 디렉터리 탐색
    d = find_case_dir_by_suffix(case_id)
    if d and (d / filename).exists():
        return d / filename

    # 2️⃣ normalize case_id 재시도
    normalized = _normalize_case_id(case_id)
    if normalized != case_id:
        d2 = find_case_dir_by_suffix(normalized)
        if d2 and (d2 / filename).exists():
            return d2 / filename

    raise HTTPException(
        status_code=404,
        detail=f"{filename} not found for case_id={case_id}",
    )
