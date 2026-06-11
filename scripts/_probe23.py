"""해설례/법제처 dcmClCdCtl=002_01/003_01 collectionName 확정"""
import sys, re, json, requests, time
sys.stdout.reconfigure(encoding="utf-8")
BASE = "https://taxlaw.nts.go.kr"
H = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}
H_XHR = {**H, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*; q=0.01"}

def call(action_id, param, warmup="/pd/USEPDI001M.do"):
    s = requests.Session(); s.headers.update(H)
    s.get(BASE + "/", timeout=10); time.sleep(0.2)
    s.get(BASE + warmup, timeout=10); time.sleep(0.2)
    payload = {"actionId": action_id, "paramData": json.dumps(param, ensure_ascii=False)}
    r = s.post(BASE + "/action.do", data=payload,
               headers={**H_XHR, "Referer": BASE + warmup}, timeout=20)
    try: return r.json()
    except: return {"_raw": r.text[:200]}

# 해설례/법제처 해석례 dcmClCdCtl 탐색
for dcm in ["002_01", "003_01", "002_01", "003_01"]:
    for cn in ["precedent,precedent_gr", "question,question_gr",
               "ela,ela_gr", "isa,isa_gr",
               "interpretation,interpretation_gr", "commentary,commentary_gr"]:
        j = call("ASIPDI002PR01", {
            "collectionName": cn,
            "sortField": "DCM_RGT_DTM/DESC", "startCount": 1, "viewCount": 3,
            "dcmClCdCtl": [dcm]
        })
        data = j.get("data") if isinstance(j, dict) else None
        if data and "ASIPDI002PR01" in data:
            d = data["ASIPDI002PR01"]
            body = d.get("body", []) if isinstance(d, dict) else []
            if body:
                print(f"  ✅✅ dcm={dcm} cn={cn}: body={len(body)}건!")
                print(f"       TTL={body[0].get('dcm',{}).get('TTL','?')[:60]}")
                print(f"       MAIN_ID={body[0].get('dcm',{}).get('MAIN_ID','?')}")
        time.sleep(0.5)

# 모든 dcm 코드를 question collection으로 탐색
print("\n=== question,question_gr 전체 dcmClCd 탐색 ===")
for dcm in ["001_04", "001_05", "001_06", "001_07", "001_08", "001_10", "002_01", "003_01"]:
    j = call("ASIPDI002PR01", {
        "collectionName": "question,question_gr",
        "sortField": "DCM_RGT_DTM/DESC", "startCount": 1, "viewCount": 2,
        "dcmClCdCtl": [dcm]
    })
    data = j.get("data") if isinstance(j, dict) else None
    if data and "ASIPDI002PR01" in data:
        d = data["ASIPDI002PR01"]
        body = d.get("body", []) if isinstance(d, dict) else []
        top = d.get("top", []) if isinstance(d, dict) else []
        print(f"  dcm={dcm}: body={len(body)}건 top={len(top)}")
        if body:
            print(f"    TTL={body[0].get('dcm',{}).get('TTL','?')[:60]}")
            print(f"    MAIN_ID={body[0].get('dcm',{}).get('MAIN_ID','?')}")
    time.sleep(0.5)

print("\n=== precedent,precedent_gr 전체 dcmClCd 탐색 ===")
for dcm in ["001_05", "001_06", "001_07", "001_08", "001_10", "002_01", "003_01"]:
    j = call("ASIPDI002PR01", {
        "collectionName": "precedent,precedent_gr",
        "sortField": "DCM_RGT_DTM/DESC", "startCount": 1, "viewCount": 2,
        "dcmClCdCtl": [dcm]
    })
    data = j.get("data") if isinstance(j, dict) else None
    if data and "ASIPDI002PR01" in data:
        d = data["ASIPDI002PR01"]
        body = d.get("body", []) if isinstance(d, dict) else []
        top = d.get("top", []) if isinstance(d, dict) else []
        print(f"  dcm={dcm}: body={len(body)}건 top={len(top)}")
        if body:
            print(f"    TTL={body[0].get('dcm',{}).get('TTL','?')[:60]}")
            print(f"    MAIN_ID={body[0].get('dcm',{}).get('MAIN_ID','?')}")
    time.sleep(0.5)
