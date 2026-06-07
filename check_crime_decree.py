import sys, re, time, requests, urllib3
urllib3.disable_warnings()

OC = "seungmi0723"
BASE = "http://www.law.go.kr/DRF"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def search_law(query):
    for attempt in range(4):
        try:
            sess = requests.Session()
            sess.verify = False
            params = {"OC": OC, "target": "lsHistory", "type": "HTML", "query": query, "display": 100, "page": 1}
            resp = sess.get(f"{BASE}/lawSearch.do", params=params, headers=HEADERS, timeout=25)
            rows = re.findall(r'MST=(\d+)[^"]*"[^>]*>([^<]+)</a>', resp.text)
            return rows
        except Exception as e:
            print(f"  attempt {attempt+1} fail: {e}")
            time.sleep(2 + attempt)
    return []

for q in ["조세범처벌법 시행령", "조세범처벌법시행령"]:
    print(f"Searching: {q}")
    rows = search_law(q)
    print(f"  => {len(rows)}개")
    for m, n in rows[:15]:
        print(f"  MST={m}: {n.strip()}")
    if rows:
        break

# Also check existing tax_crime folder
from pathlib import Path
d = Path(r"C:\Users\LG\Documents\langchain-kr\29_FINAL\law\tax_crime")
print(f"\ntax_crime folder:")
for sub in ("law", "decree", "rule"):
    p = d / sub
    if p.exists():
        cnt = len(list(p.glob("MST_*.json")))
        print(f"  {sub}: {cnt}개")
    else:
        print(f"  {sub}: 없음")
