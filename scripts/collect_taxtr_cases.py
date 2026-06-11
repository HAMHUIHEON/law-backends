"""
조세심판원 재결례 수집기 — dem_no 범위 스캔
저장: cases/taxtr/{dem_no}.json

전문: GET /mUser/common/xmlViewer.do?dem_no={no}&mode=popup&db=s
 → "[청구번호] 조심..." 패턴이 있으면 재결례로 저장

연도별 dem_no 범위 (대략):
  2021년: 190000대
  2022년: 200000대
  2023년: 205000대
  2024년: 210000대
  2025년: 215000대
  2026년: 220000대

실행:
  python scripts/collect_taxtr_cases.py                         # 2021년 이후 (190000~222850)
  python scripts/collect_taxtr_cases.py --from 215000 --to 222900  # 범위 지정
  python scripts/collect_taxtr_cases.py --workers 5             # 병렬 5개 (기본 3)
"""
from __future__ import annotations
import argparse, json, re, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
urllib3.disable_warnings()

sys.stdout.reconfigure(encoding="utf-8")

ROOT    = Path(__file__).parent.parent
OUT_DIR = ROOT / "cases" / "taxtr"
BASE_URL = "https://www.tt.go.kr"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ── 전문 수집 ──────────────────────────────────────────────────────────────────

def _strip_html(html: str) -> str:
    """HTML 태그 제거 + 공백 정규화."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def fetch_case(dem_no: int, session: requests.Session) -> dict | None:
    """xmlViewer API 호출 → 조세심판원 재결례이면 dict 반환, 아니면 None."""
    try:
        resp = session.get(
            f"{BASE_URL}/mUser/common/xmlViewer.do",
            params={"dem_no": dem_no, "mode": "popup", "db": "s"},
            timeout=15, verify=False,
        )
        resp.raise_for_status()
    except Exception:
        return None

    text = _strip_html(resp.text)

    # 조세심판원 재결례 여부 — "[청구번호] 조심 2025중2011" 형식
    case_m = re.search(r"\[청구번호\]\s*(조심\s*[\w가-힣]+)", text)
    if not case_m:
        return None

    case_no = case_m.group(1).replace(" ", "").strip()

    # 세목 / 결정유형
    tax_m   = re.search(r"\[세\s*목\]\s*(\S+)", text)
    dec_m   = re.search(r"\[결정유형\]\s*(\S+)", text)
    date_m  = re.search(r"\((\d{4}\.\d{2}\.\d{2})\)", text)
    title_m = re.search(r"\[제\s*목\]\s*(.+?)(?=\s*[-─━]{3,}|\s*\[|$)", text)
    req_m   = re.search(r"\[결정요지\]\s*(.+?)(?=\s*\[|\s{5,}|$)", text)
    law_m   = re.search(r"\[관련법령\]\s*(.+?)(?=\s*\[|\s{5,}|$)", text)

    return {
        "dem_no":        str(dem_no),
        "case_no":       case_no,
        "decision_date": date_m.group(1).strip() if date_m else "",
        "tax_type":      tax_m.group(1).strip()  if tax_m  else "",
        "decision":      dec_m.group(1).strip()  if dec_m  else "",
        "title":         title_m.group(1).strip() if title_m else "",
        "summary":       req_m.group(1).strip()[:500] if req_m else "",
        "related_laws":  law_m.group(1).strip()  if law_m  else "",
        "full_text":     text,
    }


# ── 스캔 ───────────────────────────────────────────────────────────────────────

def scan_range(start: int, end: int, workers: int, delay: float) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 이미 수집된 dem_no 로드
    existing = {int(p.stem) for p in OUT_DIR.glob("*.json") if p.stem.isdigit()}
    total_range = abs(start - end)
    todo = [n for n in range(start, end - 1, -1) if n not in existing]
    print(f"범위: {start}~{end} ({total_range}개), 기존 {len(existing)}건, 남은 {len(todo)}개", flush=True)

    found = 0
    processed = 0
    t0 = time.time()

    def _worker(no: int) -> tuple[int, dict | None]:
        sess = requests.Session()
        sess.headers.update(HEADERS)
        time.sleep(delay)
        return no, fetch_case(no, sess)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_worker, no): no for no in todo}
        for fut in as_completed(futures):
            no, case = fut.result()
            processed += 1
            if case:
                out_path = OUT_DIR / f"{no}.json"
                out_path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
                found += 1

            if processed % 100 == 0:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (len(todo) - processed) / rate if rate > 0 else 0
                print(
                    f"[{processed}/{len(todo)}] 재결례 {found}건 "
                    f"| {rate:.1f}개/s | 예상 완료까지 {eta/60:.0f}분",
                    flush=True,
                )

    elapsed = time.time() - t0
    print(f"\n🎉 완료 — {found}건 수집 / {elapsed/60:.0f}분 소요", flush=True)
    print(f"   저장: {OUT_DIR}", flush=True)


# ── 엔트리 ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=int, default=190000,
                    help="시작 dem_no (기본: 190000 ≈ 2021년)")
    ap.add_argument("--to", dest="end", type=int, default=222900,
                    help="종료 dem_no (기본: 222900 ≈ 2026년 최신)")
    ap.add_argument("--workers", type=int, default=3, help="병렬 스레드 수 (기본: 3)")
    ap.add_argument("--delay", type=float, default=0.5, help="스레드당 딜레이(초, 기본: 0.5)")
    args = ap.parse_args()

    scan_range(args.start, args.end, args.workers, args.delay)


if __name__ == "__main__":
    main()
