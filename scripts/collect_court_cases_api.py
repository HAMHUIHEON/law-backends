"""
법제처 DRF API target=prec 판례 수집

수집 대상 키워드:
  국제조세, 이전가격, 조세범처벌, 법인세, 소득세, 부가가치세,
  국세기본, 국세징수, GLOBE, 이자·배당원천징수

결과: cases/court_api/{dem_no}.json
"""
from __future__ import annotations

import json
import time
import sys
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

ROOT    = Path(__file__).parent.parent
OUT_DIR = ROOT / "cases" / "court_api"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OC          = "seungmi0723"
BASE_URL    = "http://www.law.go.kr/DRF"
DISPLAY     = 100
DELAY_SEC   = 0.8   # 요청 간 간격

KEYWORDS = [
    "이전가격",
    "국제조세",
    "조세범처벌",
    "법인세 부당행위",
    "소득세 원천징수",
    "부가가치세 매입세액",
    "국세기본법 경정청구",
    "GLOBE 최저한세",
    "특수관계자 거래",
    "이중과세방지협약",
]


def fetch_prec_list(keyword: str, page: int = 1) -> dict:
    url = (
        f"{BASE_URL}/lawSearch.do"
        f"?OC={OC}&target=prec&type=JSON"
        f"&query={quote(keyword)}&display={DISPLAY}&page={page}"
    )
    s = requests.Session()
    try:
        r = s.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"    [오류] {keyword} page={page}: {e}")
        return {}


def fetch_prec_detail(prec_id: str) -> dict:
    url = (
        f"{BASE_URL}/lawService.do"
        f"?OC={OC}&target=prec&ID={prec_id}&type=JSON"
    )
    s = requests.Session()
    try:
        r = s.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("판례", data)
    except Exception as e:
        print(f"    [오류] detail {prec_id}: {e}")
        return {}


def save_case(prec_id: str, detail: dict) -> bool:
    out_path = OUT_DIR / f"{prec_id}.json"
    if out_path.exists():
        return False
    out_path.write_text(
        json.dumps(detail, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def run() -> None:
    print("=== 법제처 DRF 판례 수집 (target=prec) ===")
    seen_ids: set[str] = set()
    total_new = 0

    for kw in KEYWORDS:
        print(f"\n[키워드] {kw}")
        page = 1
        kw_new = 0

        while True:
            data = fetch_prec_list(kw, page)
            if not data:
                break

            # 결과 파싱 — DRF JSON 구조: {"PrecSearch": {"prec": [...]}}
            prec_data = data.get("PrecSearch", data)
            items = prec_data.get("prec", [])
            if isinstance(items, dict):
                items = [items]

            if not items:
                break

            total_count = int(prec_data.get("totalCnt", 0))
            print(f"  page={page}, 결과={len(items)}/{total_count}")

            for item in items:
                prec_id = str(item.get("판례일련번호", item.get("판례ID", "")))
                if not prec_id or prec_id in seen_ids:
                    continue
                seen_ids.add(prec_id)

                # 상세 조회
                time.sleep(DELAY_SEC)
                detail = fetch_prec_detail(prec_id)
                if not detail:
                    continue

                # 기본 메타 병합
                detail.setdefault("keyword_match", kw)
                if save_case(prec_id, detail):
                    kw_new += 1
                    total_new += 1
                    title = detail.get("사건명", detail.get("판례정보일련번호", prec_id))
                    print(f"    ✅ {prec_id} {title}")

            # 다음 페이지 여부
            if page * DISPLAY >= total_count:
                break
            page += 1
            time.sleep(DELAY_SEC)

        print(f"  => {kw_new}건 신규")

    print(f"\n🎉 수집 완료 — 총 신규 {total_new}건 ({OUT_DIR})")


if __name__ == "__main__":
    run()
