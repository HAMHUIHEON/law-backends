"""
법원 판례 bravo 파이프라인 실행기

CASE/ PDF → bravo 10단계 → cache/{case_id}/
cases/court_api/ JSON → 텍스트 .txt 변환 → bravo 10단계 → cache/{case_id}/

이미 cache/{case_id}/issue_logic.json이 있으면 스킵 (캐시 기반 재개)
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

ROOT     = Path(__file__).parent.parent
CASE_DIR = ROOT / "CASE"
API_DIR  = ROOT / "cases" / "court_api"
TMP_DIR  = ROOT / "cases" / "_tmp_txt"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# bravo 파이프라인은 루트 기준 import
sys.path.insert(0, str(ROOT))
from bravo.full_pipeline import run_full_pipeline


DELAY_BETWEEN = 2  # 파이프라인 사이 대기(s)


def is_done(case_id: str) -> bool:
    """issue_logic.json 있으면 완료로 간주."""
    cache_path = ROOT / "cache" / case_id / "issue_logic.json"
    return cache_path.exists()


def save_final(case_id: str, result: dict) -> None:
    """run_full_pipeline 반환값을 cache/{case_id}/final.json에 저장."""
    from utils.cache import save_cache
    save_cache(case_id, "final.json", result)


def run_pdf_pipeline(pdf_path: Path) -> bool:
    case_id = pdf_path.stem
    if is_done(case_id):
        print(f"  [스킵] {case_id}")
        return False
    print(f"  [실행] {case_id}")
    try:
        result = run_full_pipeline(str(pdf_path))
        save_final(case_id, result)
        return True
    except Exception as e:
        print(f"  [오류] {case_id}: {e}")
        traceback.print_exc()
        return False


def api_json_to_txt(api_path: Path) -> Path:
    """DRF API JSON → 브라보 파이프라인용 .txt."""
    raw_data = json.loads(api_path.read_text(encoding="utf-8"))
    # DRF API 응답은 {"PrecService": {...}} 구조
    data = raw_data.get("PrecService", raw_data)

    # HTML br 태그 정리
    def clean(s: str) -> str:
        return s.replace("<br/>", "\n").replace("<br>", "\n").strip() if s else ""

    parts = []
    case_name = clean(data.get("사건명", ""))
    court     = clean(data.get("법원명", ""))
    case_no   = clean(data.get("사건번호", ""))
    decision  = clean(data.get("선고일자", ""))
    parts.append(f"사건명: {case_name}")
    parts.append(f"법원: {court}  사건번호: {case_no}  선고: {decision}")
    parts.append("")

    if data.get("판시사항"):
        parts.append("판시사항")
        parts.append(clean(data["판시사항"]))
        parts.append("")

    if data.get("판결요지"):
        parts.append("판결요지")
        parts.append(clean(data["판결요지"]))
        parts.append("")

    # 판례내용 = 실제 판결 전문 (주문 + 이유)
    if data.get("판례내용"):
        parts.append("판결이유")
        parts.append(clean(data["판례내용"]))
        parts.append("")

    if data.get("참조조문"):
        parts.append("참조조문")
        parts.append(clean(data["참조조문"]))
        parts.append("")

    if data.get("참조판례"):
        parts.append("참조판례")
        parts.append(clean(data["참조판례"]))
        parts.append("")

    txt_content = "\n".join(parts)
    case_id = f"api_{api_path.stem}"
    txt_path = TMP_DIR / f"{case_id}.txt"
    txt_path.write_text(txt_content, encoding="utf-8")
    return txt_path


def run_api_pipeline(api_path: Path) -> bool:
    case_id = f"api_{api_path.stem}"
    if is_done(case_id):
        print(f"  [스킵] {case_id}")
        return False
    print(f"  [실행] {case_id}")
    try:
        txt_path = api_json_to_txt(api_path)
        result = run_full_pipeline(str(txt_path))
        save_final(case_id, result)
        return True
    except Exception as e:
        print(f"  [오류] {case_id}: {e}")
        traceback.print_exc()
        return False


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="법원 판례 bravo 파이프라인")
    parser.add_argument("--source", choices=["pdf", "api", "all"], default="all")
    parser.add_argument("--limit", type=int, default=0, help="최대 처리 건수 (0=전체)")
    args = parser.parse_args()

    done_total = 0
    count = 0

    if args.source in ("pdf", "all"):
        pdfs = sorted(CASE_DIR.glob("*.pdf"))
        print(f"\n=== CASE/ PDF 파이프라인 ({len(pdfs)}건) ===")
        for pdf_path in pdfs:
            if args.limit and count >= args.limit:
                break
            ok = run_pdf_pipeline(pdf_path)
            if ok:
                done_total += 1
                time.sleep(DELAY_BETWEEN)
            count += 1

    if args.source in ("api", "all"):
        apis = sorted(API_DIR.glob("*.json")) if API_DIR.exists() else []
        print(f"\n=== DRF API 판례 파이프라인 ({len(apis)}건) ===")
        for api_path in apis:
            if args.limit and count >= args.limit:
                break
            ok = run_api_pipeline(api_path)
            if ok:
                done_total += 1
                time.sleep(DELAY_BETWEEN)
            count += 1

    print(f"\n🎉 완료 — {done_total}건 신규 처리 (cache/ 에 저장)")


if __name__ == "__main__":
    main()
