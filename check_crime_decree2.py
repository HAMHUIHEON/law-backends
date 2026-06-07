# -*- coding: utf-8 -*-
import sys, re, time, json
import requests, urllib3
from pathlib import Path

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

OC = "seungmi0723"
BASE = "http://www.law.go.kr/DRF"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fetch(query, page=1):
    for attempt in range(4):
        try:
            sess = requests.Session()
            sess.verify = False
            params = {"OC": OC, "target": "lsHistory", "type": "HTML",
                      "query": query, "display": 100, "page": page}
            resp = sess.get(f"{BASE}/lawSearch.do", params=params,
                            headers=HEADERS, timeout=25)
            rows = re.findall(r'MST=(\d+)[^"]*"[^>]*>([^<]+)</a>', resp.text)
            return rows
        except Exception as e:
            print(f"  attempt {attempt+1} fail: {e}")
            time.sleep(2 + attempt)
    return []


# 조세범처벌법 시행령 검색
for q in ["조세범처벌법 시행령", "조세범처벌법시행령"]:
    rows = fetch(q)
    print(f"[{q}] {len(rows)}개")
    for m, n in rows[:20]:
        print(f"  MST={m}: {n.strip()}")

# 조세범처벌법 전체 (시행령 포함 확인)
print("\n[조세범처벌법 전체 검색]")
rows2 = fetch("조세범처벌법")
all_names = [(m, n.strip()) for m, n in rows2]
print(f"  총 {len(rows2)}개")
for m, n in all_names:
    print(f"  MST={m}: {n}")
