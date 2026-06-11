"""조세특례제한법 DRF 검색 디버그."""
import requests, re, urllib3, sys
sys.stdout.reconfigure(encoding="utf-8")
urllib3.disable_warnings()

HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
OC = "seungmi0723"

# 실제 HTML 내용 확인
s = requests.Session(); s.verify = False
r = s.get("http://www.law.go.kr/DRF/lawSearch.do",
    params={"OC": OC, "target": "lsHistory", "type": "HTML",
            "query": "조세특례제한법", "display": 100, "page": 1},
    headers=HDR, timeout=15)
print(f"Status: {r.status_code}, 길이: {len(r.text)}")
print("=== HTML 내용 앞 2000자 ===")
print(r.text[:2000])
print("=== MST 패턴 탐색 ===")
# 모든 MST 패턴
all_mst = re.findall(r'MST[=\s]*["\']?(\d+)', r.text)
print(f"MST 번호들: {all_mst[:20]}")
# 링크 패턴 다양하게 시도
p1 = re.findall(r'"MST=(\d+)[^"]*"[^>]*>([^<]+)</a>', r.text)
p2 = re.findall(r'MST=(\d+)[^>]*>([^<]{2,50})</a>', r.text)
print(f"패턴1 결과: {len(p1)}건")
print(f"패턴2 결과: {len(p2)}건")
for mst, nm in p2[:10]:
    print(f"  MST={mst}  이름={nm.strip()}")
