"""
CASE/ 폴더 PDF → 텍스트 추출 + cases/court/{사건번호}.json 저장

파일명 패턴: {법원명}_{사건번호}.pdf
  예) 대법원_2022도13402.pdf
      서울행정법원_2018구합61208.pdf

사건번호 유형 추론:
  도/노/고합 → 형사 (조세범처벌법)
  두/누/구합/구단 → 행정 (행정소송 — 취소/무효)
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import dotenv
dotenv.load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

import pdfplumber

ROOT      = Path(__file__).parent.parent
CASE_DIR  = ROOT / "CASE"
OUT_DIR   = ROOT / "cases" / "court"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 사건유형 추론
CRIMINAL_CODES = ("도", "노", "고합", "고단", "오")       # 형사
ADMIN_CODES    = ("두", "누", "구합", "구단", "마")        # 행정


def _infer_case_type(case_no: str) -> str:
    for code in ADMIN_CODES:
        if code in case_no:
            return "ADMIN"
    for code in CRIMINAL_CODES:
        if code in case_no:
            return "CRIMINAL"
    return "UNKNOWN"


def _parse_filename(stem: str) -> dict:
    """'대법원_2022도13402' → {court, case_no, year, type}"""
    parts = stem.split("_", 1)
    court   = parts[0] if len(parts) >= 1 else ""
    case_no = parts[1] if len(parts) >= 2 else stem

    year_m = re.search(r"(\d{4})", case_no)
    year   = year_m.group(1) if year_m else ""

    return {
        "court":    court,
        "case_no":  case_no,
        "year":     year,
        "case_type": _infer_case_type(case_no),
    }


def extract_text(pdf_path: Path) -> str:
    """pdfplumber로 텍스트 추출."""
    texts = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    texts.append(t.strip())
    except Exception as e:
        return f"[추출 오류: {e}]"
    return "\n".join(texts)


def _make_summary(text: str, max_chars: int = 500) -> str:
    """첫 500자를 요약으로 사용."""
    clean = re.sub(r"\s+", " ", text).strip()
    return clean[:max_chars]


def process_pdf(pdf_path: Path) -> dict | None:
    meta = _parse_filename(pdf_path.stem)

    out_path = OUT_DIR / f"{pdf_path.stem}.json"
    if out_path.exists():
        return None  # 이미 처리됨

    text = extract_text(pdf_path)
    if len(text) < 50:
        return None

    data = {
        **meta,
        "filename": pdf_path.name,
        "summary":  _make_summary(text),
        "full_text": text,
        "char_count": len(text),
    }

    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return data


def run() -> None:
    pdfs = sorted(CASE_DIR.glob("*.pdf"))
    print(f"=== CASE PDF 텍스트 추출 ===")
    print(f"대상: {len(pdfs)}개\n")

    done = 0
    skipped = 0
    t0 = time.time()

    for pdf_path in pdfs:
        result = process_pdf(pdf_path)
        if result is None:
            skipped += 1
        else:
            done += 1
            print(f"  ✅ {pdf_path.stem} ({result['case_type']}, {result['char_count']:,}자)")

    elapsed = time.time() - t0
    print(f"\n🎉 완료 — {done}건 추출 / {skipped}건 스킵 / {elapsed:.0f}s")
    print(f"   저장: {OUT_DIR}")


if __name__ == "__main__":
    run()
