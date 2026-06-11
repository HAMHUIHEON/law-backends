import sys, re, json, requests, time
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0", "Accept-Language": "ko-KR,ko;q=0.9"}
H_XHR = {**H, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*; q=0.01"}

sess = requests.Session()
sess.headers.update(H)
sess.get(BASE + "/", timeout=10)
time.sleep(0.3)

import bs4

def call(action_id, param_data, referer="/"):
    payload = {"actionId": action_id, "paramData": json.dumps(param_data, ensure_ascii=False)}
    r = sess.post(BASE + "/action.do", data=payload,
                  headers={**H_XHR, "Referer": BASE + referer}, timeout=15)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:200]}

# ── 1) pd, qt 페이지에서 data-code 속성 추출 ──────────────────────────────────
print("=== data-code 속성 추출 (판례/질의 카테고리 코드) ===")
for page in ["/pd/USEPDI001M.do", "/qt/USEQTJ001M.do", "/af/USEAFA001M.do"]:
    r = sess.get(BASE + page, timeout=10)
    soup = bs4.BeautifulSoup(r.text, "html.parser")
    codes = [(e.get("data-code"), e.get_text(strip=True)[:30]) for e in soup.find_all(attrs={"data-code": True})]
    print(f"\n{page}:")
    for code, text in codes[:20]:
        print(f"  [{code}] {text}")
    time.sleep(0.3)

# ── 2) leftRightFilter.js 분석 ─────────────────────────────────────────────────
print("\n=== leftRightFilter.js ===")
for js_path in ["/js/leftRightFilter.js", "/js/leftRightFilter.js?v=1", "/js/common/common_st.js"]:
    r2 = sess.get(BASE + js_path, timeout=10)
    if r2.status_code == 200 and len(r2.text) > 100:
        print(f"\n{js_path} ({len(r2.text):,}자)")
        mr_ids = re.findall(r"""['"]([A-Z]{3,}[A-Z0-9]{4,}MR\d{2,3})['"]""", r2.text)
        urls = re.findall(r"""url\s*:\s*['"]([^'"]+)['"]""", r2.text)
        calls = re.findall(r"""callAction\s*\(\s*['"]([^'"]+)['"]""", r2.text)
        dcms = re.findall(r"""dcmClCd\s*[=:,]\s*['"]([^'"]+)['"]""", r2.text)
        print(f"  MR IDs: {sorted(set(mr_ids))}")
        print(f"  URLs: {sorted(set(urls))[:5]}")
        print(f"  callAction: {sorted(set(calls))[:10]}")
        print(f"  dcmClCd values: {sorted(set(dcms))}")
        # 200자 샘플
        print(f"  샘플: {r2.text[:300]}")

# ── 3) ASISTA001MR03 시도 (task.js에서 발견) ───────────────────────────────────
print("\n=== ASISTA001MR03 시도 ===")
for param in [
    {"pageIndex": 1, "pageSize": 10},
    {"pageIndex": 1, "pageSize": 10, "dcmClCd": ""},
    {"pageIndex": 1, "pageSize": 10, "searchNm": "이전가격"},
    {"pageIndex": 1, "pageSize": 10, "dcmClCd": "10"},
    {"pageIndex": 1, "pageSize": 10, "dcmClCd": "01"},
]:
    status, j = call("ASISTA001MR03", param)
    data = j.get("data", {}) if isinstance(j, dict) else {}
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and v:
                print(f"  ✅ param={param}: {len(v)}건! key={list(v[0].keys())[:5]}")
                print(f"     샘플: {json.dumps(v[0], ensure_ascii=False)[:200]}")
                break
            else:
                print(f"  ○ param={param}: {k}={str(v)[:80]}")
    time.sleep(0.3)

# ── 4) 통합검색 actionId 추측 ──────────────────────────────────────────────────
print("\n=== 통합검색 totalSearch.js 분석 ===")
r3 = sess.get(BASE + "/js/common/totalSearch.js", timeout=10)
if r3.status_code == 200:
    print(f"totalSearch.js ({len(r3.text):,}자)")
    mr_ids = re.findall(r"""['"]([A-Z]{3,}[A-Z0-9]{4,}MR\d{2,3})['"]""", r3.text)
    calls = re.findall(r"""callAction\s*\(\s*['"]([^'"]+)['"]""", r3.text)
    print(f"  MR IDs: {sorted(set(mr_ids))}")
    print(f"  callAction: {sorted(set(calls))}")
    print(f"  샘플: {r3.text[:400]}")
