# -*- coding: utf-8 -*-
import sys, re, time, json
import requests, urllib3
from pathlib import Path

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

OC = "seungmi0723"
BASE = "http://www.law.go.kr/DRF"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 이전에 캡처 못한 MST들 (조세범 처벌법, 공백 있음)
new_msts = ["224875","224843","224317","206316","181384","178140",
            "149367","141068","131388","122383","98314","91417"]

def fetch_meta(mst):
    for attempt in range(3):
        try:
            sess = requests.Session()
            sess.verify = False
            params = {"OC": OC, "target": "law", "MST": mst, "type": "JSON"}
            resp = sess.get(f"{BASE}/lawService.do", params=params, headers=HEADERS, timeout=25)
            if resp.status_code == 200 and len(resp.text) > 100:
                data = resp.json()
                info = data.get("법령", {}).get("기본정보", {})
                kind = info.get("법종구분", {})
                if isinstance(kind, dict):
                    kind = kind.get("content", "")
                return {
                    "mst": mst,
                    "name": info.get("법령명_한글", "?"),
                    "kind": kind,
                    "pdate": info.get("공포일자", "?"),
                    "pno": info.get("공포번호", "?"),
                    "eff_date": info.get("시행일자", "?"),
                }
        except Exception as e:
            print(f"  MST={mst} fail: {e}")
            time.sleep(2)
    return None

print("이전 캡처 못한 '조세범 처벌법' MST 메타 확인:")
for mst in new_msts[:6]:  # 6개만 확인
    meta = fetch_meta(mst)
    if meta:
        print(f"  MST={meta['mst']}: [{meta['kind']}] {meta['name']} ({meta['pdate']} 공포 / {meta['eff_date']} 시행)")
    time.sleep(0.3)
