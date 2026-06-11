"""
조세특례제한법 본법 전체 다운로드
구 명칭 '조세감면규제법' 포함, 법종구분='법' 기준으로 필터
"""
from __future__ import annotations
import json, re, sys, time
from pathlib import Path
import requests, urllib3
urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

ROOT    = Path(__file__).parent.parent
OUT_DIR = ROOT / "law" / "joseteukrejehan" / "law"
OC      = "seungmi0723"
BASE    = "http://www.law.go.kr/DRF"
HDR     = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

OUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_mst_list_all(query: str) -> list[str]:
    """법령명 필터 없이 검색 결과 MST 전체 반환."""
    msts, page = [], 1
    while True:
        s = requests.Session(); s.verify = False
        r = s.get(f"{BASE}/lawSearch.do",
                  params={"OC": OC, "target": "lsHistory", "type": "HTML",
                          "query": query, "display": 100, "page": page},
                  headers=HDR, timeout=15)
        rows = re.findall(r'MST=(\d+)[^>]*>([^<]{2,60})</a>', r.text)
        if not rows:
            break
        msts.extend(mst for mst, _ in rows)
        print(f"  page {page}: {len(rows)}건 (예시: {rows[0][1].strip()[:30]})")
        if len(rows) < 100:
            break
        page += 1
        time.sleep(0.3)
    return msts


def fetch_json(mst: str) -> dict | None:
    for i in range(3):
        try:
            s = requests.Session(); s.verify = False
            r = s.get(f"{BASE}/lawService.do",
                      params={"OC": OC, "target": "law", "MST": mst, "type": "JSON"},
                      headers=HDR, timeout=20)
            if r.status_code == 200 and len(r.text) > 100:
                return r.json()
        except Exception:
            if i < 2: time.sleep(1 + i)
    return None


def extract_meta(data: dict) -> dict | None:
    try:
        root = data.get(next(iter(data)), {})
        info = root.get("기본정보", {})
        law_type = info.get("법종구분", "")
        if isinstance(law_type, dict):
            law_type = law_type.get("content", "")
        pno   = str(info.get("공포번호", "")).strip()
        pdate = str(info.get("공포일자", "")).strip()
        if not (pno and pdate):
            return None
        return {
            "pno":      pno,
            "pdate":    pdate,
            "eff_date": str(info.get("시행일자", "")).strip(),
            "law_name": str(info.get("법령명_한글") or "").strip(),
            "law_type": law_type,
            "mst":      str(info.get("법령MST") or "").strip(),
            "law_id":   str(info.get("법령ID") or "").strip(),
        }
    except Exception:
        return None


def main():
    print("=== 조세특례제한법 본법 다운로드 ===\n")

    # MST 목록 수집 (구 명칭 포함)
    all_msts = []
    for query in ["조세특례제한법", "조세감면규제법"]:
        print(f"검색: {query}")
        msts = fetch_mst_list_all(query)
        all_msts.extend(msts)
        print(f"  → {len(msts)}건")
    all_msts = list(dict.fromkeys(all_msts))  # 중복 제거
    print(f"\n총 {len(all_msts)}개 MST")

    index: dict[str, dict] = {}
    law_count = 0
    skip_count = 0

    for i, mst in enumerate(all_msts, 1):
        fp = OUT_DIR / f"MST_{mst}.json"

        if fp.exists():
            data = json.loads(fp.read_text(encoding="utf-8"))
        else:
            data = fetch_json(mst)
            if not data:
                print(f"  [{i}/{len(all_msts)}] MST={mst} 다운로드 실패")
                continue
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            time.sleep(0.15)

        meta = extract_meta(data)
        if not meta:
            skip_count += 1
            continue

        # 법종구분이 "법"인 것만
        ltype = meta["law_type"]
        is_law = ltype in ("법", "법률") or (not any(k in ltype for k in ["시행령", "시행규칙", "규정", "규칙", "령"]))
        if not is_law:
            skip_count += 1
            continue

        law_count += 1
        pno_key = meta["pno"].lstrip("0") or "0"
        index[pno_key] = {
            "version_key": f"{meta['pdate']}_{meta['pno']}",
            "pdate":    meta["pdate"],
            "pno":      meta["pno"],
            "eff_date": meta["eff_date"],
            "law_name": meta["law_name"],
            "mst":      meta["mst"],
            "file":     f"MST_{mst}.json",
            "law_id":   meta["law_id"],
        }
        if i % 20 == 0 or i == len(all_msts):
            print(f"  [{i}/{len(all_msts)}] 법={law_count}건 (최근: {meta['law_name']} {meta['pdate']})")

    idx_path = OUT_DIR / "_version_index.json"
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    dates = sorted(v["pdate"] for v in index.values())
    print(f"\n✅ {len(index)}개 버전 ({dates[0]}~{dates[-1]}) 저장")
    print(f"  법 외 스킵: {skip_count}건")
    print(f"  저장 위치: {OUT_DIR}")


if __name__ == "__main__":
    main()
