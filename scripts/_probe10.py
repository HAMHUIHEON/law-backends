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

def call(action_id, param, referer="/"):
    payload = {"actionId": action_id, "paramData": json.dumps(param, ensure_ascii=False)}
    r = sess.post(BASE + "/action.do", data=payload,
                  headers={**H_XHR, "Referer": BASE + referer}, timeout=15)
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:200]}

def check(action_id, param, label=""):
    j = call(action_id, param)
    data = j.get("data", {}) if isinstance(j, dict) else {}
    status = j.get("status", "?") if isinstance(j, dict) else "?"
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and v:
                print(f"  ✅ [{label or action_id}] {len(v)}건! key={list(v[0].keys())[:5]}")
                if v:
                    print(f"     샘플: {json.dumps(v[0], ensure_ascii=False)[:200]}")
                return True
            elif isinstance(v, dict):
                cnt = v.get("totalCount") or v.get("total") or v.get("cnt")
                if cnt and int(str(cnt)) > 0:
                    print(f"  ✅ [{label or action_id}] totalCount={cnt}  keys={list(v.keys())[:8]}")
                    return True
    if status not in ["SUCCESS", "?"]:
        pass  # 에러는 출력 안 함
    return False

# ── 1) pd 페이지에서 dcmClCd로 직접 검색 ───────────────────────────────────────
print("=== dcmClCd 기반 검색 (pd 카테고리) ===")
dcm_codes = ["001_09", "001_05", "001_06", "001_07", "001_08", "001_10"]
# 가능한 list actionId 패턴 (pd 섹션)
action_ids_pd = [
    "ASISTA001MR03",
    "ASISTA001MR01",
    "ASISTA001MR02",
    "ASISTA002MR01",
    "ASISTA003MR01",
    "ASMSDG002MR01",  # common_st.js에서 발견
    "ASMSDG002MR02",
]

for dcm in dcm_codes[:2]:  # 판례(001_09), 과세적부(001_05)만
    for aid in action_ids_pd:
        found = check(aid, {"pageIndex": 1, "pageSize": 5, "dcmClCd": dcm}, f"{aid}+{dcm}")
        if found:
            break
        time.sleep(0.2)

# ── 2) qt 페이지 사전답변 검색 ───────────────────────────────────────────────────
print("\n=== dcmClCd 기반 검색 (qt 카테고리) ===")
sess.get(BASE + "/qt/USEQTJ001M.do", timeout=10)
action_ids_qt = [
    "ASIAFA001MR01",
    "ASIAFB001MR01",
    "ASIQT0001MR01",
    "ASIQTJ001MR01",
    "ASISTA001MR03",
]
for dcm in ["001_01", "001_02", "001_03"]:
    for aid in action_ids_qt:
        found = check(aid, {"pageIndex": 1, "pageSize": 5, "dcmClCd": dcm}, f"{aid}+{dcm}")
        time.sleep(0.2)

# ── 3) ntlis.js 전체 분석 ──────────────────────────────────────────────────────
print("\n=== ntlis.js 전체 actionId 추출 ===")
r = sess.get(BASE + "/js/ntlis.js", timeout=10)
text = r.text
mr_ids = re.findall(r"""['"]([A-Z]{3,}[A-Z0-9]{4,}MR\d{2,3})['"]""", text)
print(f"  발견된 MR IDs: {sorted(set(mr_ids))}")
# dcmClCd 참조
dcm_refs = re.findall(r"""dcmClCd[^;,\n]{0,60}""", text)
for ref in dcm_refs[:10]:
    print(f"  dcmClCd ref: {ref.strip()}")
# action 패턴
action_refs = re.findall(r"""action[^;,\n\'"]{0,100}""", text, re.IGNORECASE)
for ref in action_refs[:5]:
    print(f"  action ref: {ref.strip()[:80]}")

# ── 4) 전체 탐색: MR01 부터 MR10까지 순열 시도 ────────────────────────────────
print("\n=== 체계적 actionId 순열 (판례 dcmClCd=001_09) ===")
prefixes = ["ASINTST", "ASIPDJ", "ASIPREC", "ASIPRJ", "ASIDCM",
            "ASISRH", "ASIDCMJ", "ASINTL", "ASIJDG", "ASIJUD"]
for prefix in prefixes:
    for n in ["001", "002", "003"]:
        for m in ["MR01", "MR02", "MR03"]:
            aid = f"{prefix}{n}{m}"
            j2 = call(aid, {"pageIndex": 1, "pageSize": 3, "dcmClCd": "001_09"})
            data = j2.get("data", {}) if isinstance(j2, dict) else {}
            status = j2.get("status", "") if isinstance(j2, dict) else ""
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list) and v:
                        print(f"  ✅✅ {aid}: {len(v)}건! {list(v[0].keys())[:5]}")
            time.sleep(0.15)
