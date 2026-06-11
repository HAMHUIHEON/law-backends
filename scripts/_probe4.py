import sys, re, json, requests, time
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": BASE + "/",
    "X-Requested-With": "XMLHttpRequest",
}

# 1) common.js 전체 저장해서 /action.do 호출 패턴 분석
r = requests.get(BASE + "/js/common/common.js", headers=H, timeout=15)
js = r.text

# action.do 주변 코드 추출
idx = js.find("/action.do")
print("=== /action.do 주변 코드 (±300자) ===")
print(js[max(0, idx-300):idx+300])
print()

# serviceId 패턴 추출
service_ids = re.findall(r"""serviceId\s*[=:]\s*['"]([^'"]+)['"]""", js)
print(f"=== serviceId 패턴 ({len(service_ids)}개) ===")
for s in sorted(set(service_ids)):
    print(f"  {s}")

# 2) 페이지별 JS 파일에서 serviceId 추출
print("\n=== 페이지별 JS (pd/qt/is/el 관련) ===")
page_urls = ["/prec/list.do", "/expc/list.do"]
for page in page_urls:
    r2 = requests.get(BASE + page, headers={**H, "X-Requested-With": ""}, timeout=10)
    # 인라인 스크립트에서 serviceId 찾기
    sids = re.findall(r"""serviceId\s*[=:,]\s*['"]([^'"]+)['"]""", r2.text)
    actions = re.findall(r"""action\s*[=:,]\s*['"]([^'"]+)['"]""", r2.text)
    print(f"\n{page}:")
    for s in set(sids):
        print(f"  serviceId: {s}")
    for a in set(actions):
        if ".do" in a or "action" in a.lower():
            print(f"  action: {a}")
    time.sleep(0.3)

# 3) /action.do 직접 프로브 - 일반적인 파라미터 시도
print("\n=== /action.do 직접 프로브 ===")
H_POST = {**H, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}

test_payloads = [
    {"serviceId": "USEPDASRH001", "pageIndex": 1, "pageSize": 10},
    {"serviceId": "USEPDALIST", "pageIndex": 1, "pageSize": 10},
    {"serviceId": "PD_LIST", "pageIndex": 1, "pageSize": 10},
    {"serviceId": "PREC_LIST", "pageIndex": 1, "pageSize": 10},
    {"cmd": "list", "type": "prec", "pageIndex": 1, "pageSize": 10},
    {"action": "list", "category": "prec", "pageIndex": 1},
]

for payload in test_payloads:
    r3 = requests.post(BASE + "/action.do", data=payload, headers=H_POST, timeout=10)
    is_json = False
    preview = ""
    try:
        j = r3.json()
        is_json = True
        preview = str(list(j.keys()) if isinstance(j, dict) else j[:1])[:100]
    except Exception:
        pass
    status = "✅" if (is_json and r3.status_code == 200) else "✗ "
    print(f"  {status} {r3.status_code} payload={list(payload.keys())[:3]}  json={is_json}  {preview}")
    time.sleep(0.3)
