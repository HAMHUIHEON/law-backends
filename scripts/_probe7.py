import sys, re, json, requests, time
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0", "Accept-Language": "ko-KR,ko;q=0.9"}
H_XHR = {**H, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*; q=0.01"}

sess = requests.Session()
sess.headers.update(H)
sess.get(BASE + "/", timeout=10)
sess.get(BASE + "/pd/USEPDI001M.do", timeout=10)
time.sleep(0.5)

def call(action_id, param_data, referer="/pd/USEPDI001M.do"):
    payload = {"actionId": action_id, "paramData": json.dumps(param_data, ensure_ascii=False)}
    r = sess.post(BASE + "/action.do", data=payload,
                  headers={**H_XHR, "Referer": BASE + referer}, timeout=15)
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:300]}

# ── 1) 판례 리스트 전체 구조 확인 ──────────────────────────────────────────────
print("=== 판례 ASISTZ001MR01 상세 ===")
r = call("ASISTZ001MR01", {"pageIndex": 1, "pageSize": 5, "searchNm": ""})
data = r.get("data", {}).get("ASISTZ001MR01", [])
if isinstance(data, list) and data:
    print(f"  건수 확인 (pageSize=5): {len(data)}건 반환")
    print(f"  첫 번째 레코드 keys: {list(data[0].keys())}")
    print(f"  샘플: {json.dumps(data[0], ensure_ascii=False)[:300]}")
    # 전체 건수 확인
    r2 = call("ASISTZ001MR01", {"pageIndex": 1, "pageSize": 1, "searchNm": ""})
    d2 = r2.get("data", {})
    print(f"  전체 data keys: {list(d2.keys())}")
else:
    print(f"  data: {str(data)[:200]}")
    print(f"  전체 data keys: {list(r.get('data', {}).keys())}")

# ── 2) 판례 페이지 HTML에서 추가 actionId 찾기 ──────────────────────────────────
print("\n=== 판례 페이지 HTML에서 actionId 추출 ===")
page_r = sess.get(BASE + "/pd/USEPDI001M.do", timeout=10)
html = page_r.text
# callAction( 패턴
calls = re.findall(r"""callAction\s*\(\s*['"]([^'"]+)['"]""", html)
print(f"  callAction 호출: {sorted(set(calls))}")
# action.ntlis 패턴
action_patterns = re.findall(r"""['"]([ASI][A-Z0-9]{6,}MR\d{2})['"]""", html)
print(f"  MR 패턴: {sorted(set(action_patterns))[:20]}")

# ── 3) 다른 카테고리 페이지에서 list actionId 찾기 ──────────────────────────────
print("\n=== 카테고리별 actionId 추출 ===")
category_pages = [
    ("/af/USEAFA001M.do", "사전답변"),
    ("/af/USEAFB001M.do", "질의회신"),
    ("/el/USEELA001M.do", "해설례"),
    ("/is/USEISA001M.do", "해석례"),
    ("/qt/USEQTJ001M.do", "질의회신(qt)"),
]
for path, name in category_pages:
    r3 = sess.get(BASE + path, timeout=10)
    html3 = r3.text
    mr_ids = re.findall(r"""['"]([ASI][A-Z0-9]{6,}MR\d{2})['"]""", html3)
    calls3 = re.findall(r"""callAction\s*\(\s*['"]([^'"]+)['"]""", html3)
    all_ids = sorted(set(mr_ids + calls3))
    print(f"\n{name} ({path}):")
    for i in all_ids:
        print(f"  {i}")
    time.sleep(0.3)

# ── 4) 사전답변 list 올바른 파라미터 찾기 ──────────────────────────────────────
print("\n=== 사전답변 list 파라미터 탐색 ===")
af_page_r = sess.get(BASE + "/af/USEAFA001M.do", timeout=10)
# form hidden inputs, data-* 속성
import bs4
soup = bs4.BeautifulSoup(af_page_r.text, "html.parser")
for elem in soup.find_all(attrs={"data-action": True}):
    print(f"  data-action: {elem.get('data-action')} tag={elem.name}")
for inp in soup.find_all("input", type="hidden"):
    if inp.get("name") and inp.get("value"):
        print(f"  hidden: name={inp.get('name')} value={inp.get('value')[:50]}")
