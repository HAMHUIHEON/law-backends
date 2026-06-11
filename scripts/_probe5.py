import sys, re, json, requests, time
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": BASE + "/",
}
H_XHR = {**H, "X-Requested-With": "XMLHttpRequest",
          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}

# 1) 판례/해설례 전용 .do 페이지에서 actionId 추출
pages = [
    "/pd/USEPDI001M.do",   # 판례 index(?)
    "/qt/USEQTJ001M.do",   # 질의
    "/is/USEISA001M.do",   # 해석례
    "/is/USEISA003M.do",
    "/el/USEELA001M.do",   # 해설례(?)
    "/af/USEAFA001M.do",   # 사전답변(?)
    "/af/USEAFB001M.do",
]

all_action_ids = set()

for path in pages:
    r = requests.get(BASE + path, headers=H, timeout=10)
    if r.status_code != 200:
        print(f"{path} → {r.status_code}")
        continue
    text = r.text
    # actionId 값 추출
    ids = re.findall(r"""actionId\s*[=:,]\s*['"]([A-Z0-9_]+)['"]""", text)
    ids2 = re.findall(r"""'([A-Z]{3,}[A-Z0-9_]{4,})'""", text)  # 대문자 코드 패턴
    # JS 파일 참조 추출
    scripts = re.findall(r"""src=['"]([^'"]+\.js[^'"]*)['"]""", text)
    print(f"\n{path} ({r.status_code}, {len(text):,}자)")
    if ids:
        print(f"  actionId: {ids}")
        all_action_ids.update(ids)
    if ids2:
        filtered = [i for i in ids2 if len(i) > 6]
        print(f"  code-like: {filtered[:10]}")
    for s in scripts:
        if "vendor" not in s:
            print(f"  SCRIPT: {s}")
    time.sleep(0.3)

print(f"\n=== 수집된 actionId ===")
for a in sorted(all_action_ids):
    print(f"  {a}")

# 2) /action.do - 올바른 파라미터 구조로 재시도
print("\n=== /action.do 올바른 구조로 재시도 ===")
import json as j_mod

test_cases = [
    ("USEPDASRH001", {}),
    ("USEPDALIST001", {"pageIndex": 1, "pageSize": 10}),
    ("PREC_LIST", {"pageIndex": 1, "pageSize": 10}),
    ("USEPDAJ001", {"pageIndex": 1, "pageSize": 10, "searchCondition": ""}),
    ("USEPDA001J", {"pageIndex": 1, "pageSize": 10}),
]

for action_id, param_data in test_cases:
    payload = {
        "actionId": action_id,
        "paramData": j_mod.dumps(param_data, ensure_ascii=False)
    }
    r2 = requests.post(BASE + "/action.do", data=payload, headers=H_XHR, timeout=10)
    try:
        jd = r2.json()
        keys = list(jd.keys()) if isinstance(jd, dict) else type(jd).__name__
        print(f"  ✅ actionId={action_id}  keys={keys}")
    except Exception:
        body = r2.text[:100].replace("\n", " ")
        print(f"  ✗  actionId={action_id}  {r2.status_code}  {body}")
    time.sleep(0.3)
