# -*- coding: utf-8 -*-
"""조세범처벌법 누락 MST 12개 다운로드 및 인덱스 재빌드"""
import sys, json, time
import requests, urllib3
from pathlib import Path

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

OC = "seungmi0723"
BASE = "http://www.law.go.kr/DRF"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
OUT_DIR = Path(r"C:\Users\LG\Documents\langchain-kr\29_FINAL\law\tax_crime\law")

MISSING_MSTS = [
    "224875","224843","224317","206316","181384","178140",
    "149367","141068","131388","122383","98314","91417"
]


def fetch_law_version(mst):
    for attempt in range(4):
        try:
            sess = requests.Session()
            sess.verify = False
            params = {"OC": OC, "target": "law", "MST": mst, "type": "JSON"}
            resp = sess.get(f"{BASE}/lawService.do", params=params, headers=HEADERS, timeout=25)
            if resp.status_code == 200 and len(resp.text) > 100:
                return resp.json()
        except Exception as e:
            print(f"  attempt {attempt+1} fail: {e}")
            time.sleep(1 + attempt)
    return None


def extract_meta(data):
    info = data.get("법령", {}).get("기본정보", {})
    kind = info.get("법종구분", {})
    if isinstance(kind, dict):
        kind = kind.get("content", "")
    return {
        "mst": info.get("법령MST", ""),
        "law_name": info.get("법령명_한글", ""),
        "kind": kind,
        "pdate": info.get("공포일자", ""),
        "pno": info.get("공포번호", ""),
        "eff_date": info.get("시행일자", ""),
    }


OUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"조세범처벌법 누락 MST {len(MISSING_MSTS)}개 다운로드 시작")
downloaded = 0
for mst in MISSING_MSTS:
    outf = OUT_DIR / f"MST_{mst}.json"
    if outf.exists():
        print(f"  MST={mst}: 이미 존재, skip")
        downloaded += 1
        continue
    data = fetch_law_version(mst)
    if data:
        meta = extract_meta(data)
        data["_meta"] = meta
        outf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"  MST={mst}: {meta['law_name']} {meta['pdate']} 저장됨")
        downloaded += 1
    else:
        print(f"  MST={mst}: 다운로드 실패")
    time.sleep(0.3)

print(f"\n완료: {downloaded}/{len(MISSING_MSTS)}개 저장")

# 인덱스 재빌드
print("\n인덱스 재빌드...")
index = {}
for f in sorted(OUT_DIR.glob("MST_*.json")):
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        meta = data.get("_meta") or {}
        if not meta:
            info = data.get("법령", {}).get("기본정보", {})
            kind_raw = info.get("법종구분", {})
            kind = kind_raw.get("content", "") if isinstance(kind_raw, dict) else kind_raw
            meta = {
                "mst": info.get("법령MST", ""),
                "law_name": info.get("법령명_한글", ""),
                "kind": kind,
                "pdate": info.get("공포일자", ""),
                "pno": info.get("공포번호", ""),
                "eff_date": info.get("시행일자", ""),
            }
        pno = str(meta.get("pno", "")).lstrip("0")
        if pno:
            index[pno] = {
                "version_key": f"LAW_{meta.get('pdate','')}_{pno}",
                "pdate": meta.get("pdate", ""),
                "pno": pno,
                "eff_date": meta.get("eff_date", ""),
                "law_name": meta.get("law_name", ""),
                "mst": meta.get("mst", ""),
                "file": f.name,
            }
    except Exception as e:
        print(f"  {f.name}: 오류 {e}")

idx_f = OUT_DIR / "_version_index.json"
idx_f.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"인덱스 완료: {len(index)}개 항목 -> {idx_f}")
