import sys, re, json, requests, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0", "Accept-Language": "ko-KR,ko;q=0.9"}
H_XHR = {**H, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*; q=0.01"}

sess = requests.Session()
sess.headers.update(H)
sess.get(BASE + "/", timeout=10)
time.sleep(0.3)

# ── 1) /pd/USEPDI001M.do 전체 HTML 저장 후 분석 ──────────────────────────────
print("=== /pd/USEPDI001M.do HTML 전체 분석 ===")
r = sess.get(BASE + "/pd/USEPDI001M.do", timeout=15)
html = r.text
Path("taxlaw/pd_page.html").write_text(html, encoding="utf-8")
print(f"  HTML 크기: {len(html):,}자 → taxlaw/pd_page.html 저장")

# callAction 패턴 모두
calls = re.findall(r"""callAction\s*\(\s*['"]([^'"]+)['"]""", html)
print(f"  callAction: {sorted(set(calls))}")

# Ntlis.call 패턴
ntlis_calls = re.findall(r"""Ntlis\.call\s*\(\s*['"]([^'"]+)['"]""", html)
print(f"  Ntlis.call: {sorted(set(ntlis_calls))}")

# Biz. 패턴
biz_calls = re.findall(r"""Biz\.[a-zA-Z]+\s*\(\s*['"]([^'"]+MR[^'"]+)['"]""", html)
print(f"  Biz.*MR: {sorted(set(biz_calls))}")

# 모든 MR 패턴 (대문자 시작, MR01-MR10)
all_mr = re.findall(r"""['"]([A-Z]{2,}[A-Z0-9]{3,}MR\d{2})['"]""", html)
print(f"  전체 MR IDs ({len(set(all_mr))}개): {sorted(set(all_mr))}")

# Handlebars 템플릿 추출 (type="text/x-handlebars-template" or similar)
import bs4
soup = bs4.BeautifulSoup(html, "html.parser")
templates = soup.find_all("script", attrs={"type": re.compile("handlebars|template", re.I)})
print(f"  Handlebars 템플릿: {len(templates)}개")
for t in templates[:3]:
    content = t.get_text()[:200]
    mr_in_t = re.findall(r"""[A-Z]{2,}[A-Z0-9]{3,}MR\d{2}""", content)
    print(f"    id={t.get('id')} MR={mr_in_t} 내용={content[:100]}")

# ── 2) /qt/USEQTJ001M.do 동일 분석 ──────────────────────────────────────────
print("\n=== /qt/USEQTJ001M.do HTML 분석 ===")
r2 = sess.get(BASE + "/qt/USEQTJ001M.do", timeout=15)
html2 = r2.text
Path("taxlaw/qt_page.html").write_text(html2, encoding="utf-8")

all_mr2 = re.findall(r"""['"]([A-Z]{2,}[A-Z0-9]{3,}MR\d{2})['"]""", html2)
print(f"  전체 MR IDs ({len(set(all_mr2))}개): {sorted(set(all_mr2))}")
ntlis2 = re.findall(r"""Ntlis\.call\s*\(\s*['"]([^'"]+)['"]""", html2)
print(f"  Ntlis.call: {sorted(set(ntlis2))}")

# data-action-id 속성
for e in soup.find_all(attrs={"data-action-id": True})[:10]:
    print(f"  data-action-id={e.get('data-action-id')}")

# ── 3) 전혀 다른 접근: /action.do에 JSON body로 시도 ──────────────────────────
print("\n=== /action.do JSON body 방식 시도 ===")
# 일부 사이트는 JSON Content-Type 요구
for action_id in ["ASISTA001MR03", "ASIPDJ001MR01", "ASDCM001MR01"]:
    r3 = sess.post(BASE + "/action.do",
                   json={"actionId": action_id, "paramData": {"pageIndex": 1, "pageSize": 5, "dcmClCd": "001_09"}},
                   headers={**H, "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json",
                            "Accept": "application/json"},
                   timeout=10)
    try:
        j = r3.json()
        data = j.get("data", {})
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list) and v:
                    print(f"  ✅ JSON body {action_id}: {len(v)}건!")
                    break
            else:
                print(f"  ○ JSON body {action_id}: {j.get('status')} data={str(data)[:60]}")
    except Exception:
        print(f"  ✗ JSON body {action_id}: {r3.status_code}")
    time.sleep(0.3)

# ── 4) ntlis.js가 런타임에 로드하는 추가 JS 파일 탐색 ────────────────────────
print("\n=== ntlis.js 내에서 추가 JS 로드 패턴 ===")
ntlis_r = sess.get(BASE + "/js/ntlis.js", timeout=10)
ntlis_text = ntlis_r.text
print(f"  ntlis.js 전체 내용 (처음 3000자):")
print(ntlis_text[:3000])
