import sys, re, json, requests, time
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 1) 세션 초기화
sess = requests.Session()
sess.headers.update(H)
sess.get(BASE + "/", timeout=10)
sess.get(BASE + "/prec/list.do", timeout=10)
time.sleep(0.5)

# 2) 발견한 실제 actionId로 /action.do 호출
H_XHR = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": BASE + "/pd/USEPDI001M.do",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# 각 카테고리별 actionId - MR01 = list, MR02 = detail 패턴 추정
action_map = {
    "판례_list":    ("ASISTZ001MR01", {"pageIndex": 1, "pageSize": 10, "searchNm": ""}),
    "판례_detail":  ("ASISTZ002MR01", {"docId": ""}),
    "판례_alt":     ("ASISTZ003MR01", {"pageIndex": 1, "pageSize": 10}),
    "사전답변_list": ("ASIAFA001MR01", {"pageIndex": 1, "pageSize": 10}),
    "사전답변_dtl":  ("ASIAFA001MR02", {"docId": ""}),
    "질의회신_list": ("ASIAFB001MR01", {"pageIndex": 1, "pageSize": 10}),
    "질의회신_dtl":  ("ASIAFB001MR02", {"docId": ""}),
    "해설례_list":  ("ASIELA001MR01", {"pageIndex": 1, "pageSize": 10}),
    "해설례_dtl":   ("ASIELA001MR02", {"docId": ""}),
    "해석례_list1": ("ASEISA001MR01", {"pageIndex": 1, "pageSize": 10}),
    "해석례_list2": ("ASEISA001MR02", {"pageIndex": 1, "pageSize": 10}),
    "법제처_list":  ("ASEISA003MR01", {"pageIndex": 1, "pageSize": 10}),
}

results = {}
for name, (action_id, param_data) in action_map.items():
    payload = {
        "actionId": action_id,
        "paramData": json.dumps(param_data, ensure_ascii=False)
    }
    r = sess.post(BASE + "/action.do", data=payload, headers=H_XHR, timeout=10)
    is_json = False
    info = ""
    try:
        j = r.json()
        is_json = True
        if isinstance(j, dict):
            info = f"keys={list(j.keys())}"
            total = j.get("totalCount") or j.get("total") or j.get("cnt") or "?"
            info += f"  total={total}"
        else:
            info = str(j)[:80]
        results[name] = {"actionId": action_id, "keys": list(j.keys()) if isinstance(j, dict) else [], "sample": j}
    except Exception:
        body = r.text[:150].replace("\n", " ").strip()
        info = f"not json: {body[:80]}"
    icon = "✅" if is_json else "✗ "
    print(f"{icon} [{name}] {action_id}")
    print(f"     {info}")
    time.sleep(0.4)

# 3) 성공한 것들 상세 출력
print("\n=== 성공한 actionId JSON 샘플 ===")
for name, data in results.items():
    print(f"\n[{name}] {data['actionId']}")
    sample = data['sample']
    if isinstance(sample, dict):
        for k, v in list(sample.items())[:5]:
            if isinstance(v, list) and v:
                print(f"  {k}: {str(v[0])[:100]}")
            else:
                print(f"  {k}: {str(v)[:100]}")
