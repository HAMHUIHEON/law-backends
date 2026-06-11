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

# ── 1) 판례 전용 페이지 /prec/list.do 깊은 분석 ───────────────────────────────
print("=== /prec/list.do Handlebars 템플릿 + actionId ===")
r = sess.get(BASE + "/prec/list.do", timeout=10)
html = r.text

# Handlebars 템플릿 내부의 actionId
mr_ids = re.findall(r"""['"]([A-Z]{3,}[A-Z0-9]{4,}MR\d{2,3})['"]""", html)
print(f"  MR 패턴 ID: {sorted(set(mr_ids))}")

# task.js 같은 페이지별 JS 파일 확인
scripts = re.findall(r"""src=['"]([^'"]+\.js[^'"]*)['"]""", html)
for s in scripts:
    if "vendor" not in s:
        print(f"  SCRIPT: {s}")

# ── 2) 판례 관련 .do URL 패턴 추출
print("\n=== 판례 전용 .do URLs ===")
dos = list({d.split("?")[0] for d in re.findall(r"""['"]([^'"]*\.do[^'"?#\s]{0,60})['"]""", html) if "/" in d})
for d in sorted(dos):
    if "prec" in d.lower() or "/pd/" in d:
        print(f"  {d}")

# ── 3) task.js 파일이 있다면 가져오기 (판례 페이지 전용 로직)
for js_path in ["/js/task.js", "/js/task.js?v=1", "/js/precList.js", "/js/prec.js"]:
    r2 = sess.get(BASE + js_path, timeout=10)
    if r2.status_code == 200 and len(r2.text) > 100:
        print(f"\n=== {js_path} ({len(r2.text):,}자) ===")
        mr_in_js = re.findall(r"""['"]([A-Z]{3,}[A-Z0-9]{4,}MR\d{2,3})['"]""", r2.text)
        url_in_js = re.findall(r"""url\s*:\s*['"]([^'"]+)['"]""", r2.text)
        calls_in_js = re.findall(r"""callAction\s*\(\s*['"]([^'"]+)['"]""", r2.text)
        print(f"  MR IDs: {sorted(set(mr_in_js))}")
        print(f"  URLs: {sorted(set(url_in_js))[:10]}")
        print(f"  callAction: {sorted(set(calls_in_js))[:10]}")
        # 처음 500자 출력
        print(f"  첫 500자: {r2.text[:500]}")
    time.sleep(0.2)

# ── 4) 판례 검색 actionId 추측 시도 ─────────────────────────────────────────────
print("\n=== 판례 검색 actionId 무차별 시도 ===")
# 패턴: ASI + [카테고리] + 001/002/003 + MR01
# 판례 = PD (판결) 또는 PR (prec)
guesses = [
    ("ASIPDJ001MR01", {"pageIndex": 1, "pageSize": 5}),
    ("ASIPRJ001MR01", {"pageIndex": 1, "pageSize": 5}),
    ("ASIPRC001MR01", {"pageIndex": 1, "pageSize": 5}),
    ("ASINTSTMR01",   {"pageIndex": 1, "pageSize": 5}),
    ("ASISRH001MR01", {"pageIndex": 1, "pageSize": 5, "searchNm": "이전가격"}),
    ("ASISRH002MR01", {"pageIndex": 1, "pageSize": 5, "searchNm": "이전가격"}),
    # 과세기준자문
    ("ASIAGV001MR01", {"pageIndex": 1, "pageSize": 5}),
    ("ASICNS001MR01", {"pageIndex": 1, "pageSize": 5}),
    ("ASITAX001MR01", {"pageIndex": 1, "pageSize": 5}),
    # 해석례 직접
    ("ASEISA001MR01", {"pageIndex": 1, "pageSize": 5, "searchNm": ""}),
    ("ASEISA001MR04", {"pageIndex": 1, "pageSize": 5}),
]

for action_id, param in guesses:
    payload = {"actionId": action_id, "paramData": json.dumps(param, ensure_ascii=False)}
    r3 = sess.post(BASE + "/action.do", data=payload, headers=H_XHR, timeout=8)
    try:
        j = r3.json()
        status = j.get("status", "?")
        data = j.get("data", {})
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list) and len(v) > 0:
                    print(f"  ✅ {action_id}: {len(v)}건 반환! keys={list(v[0].keys())[:5]}")
                    break
                elif isinstance(v, dict) and "totalCount" in str(v):
                    print(f"  ✅ {action_id}: totalCount 있음! {str(v)[:100]}")
                    break
            else:
                if status == "SUCCESS":
                    print(f"  ○  {action_id}: SUCCESS but no list  data={str(data)[:60]}")
                else:
                    print(f"  ✗  {action_id}: {status}")
        else:
            print(f"  ✗  {action_id}: data={str(data)[:60]}")
    except Exception:
        print(f"  ✗  {action_id}: not json / {r3.status_code}")
    time.sleep(0.3)
