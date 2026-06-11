"""ASIAFA001MR01 atDVOList 추출 + ASIPDI002PR01 판례 전체 필드"""
import sys, re, json, requests, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
     "Accept-Language": "ko-KR,ko;q=0.9"}
H_XHR = {**H, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*; q=0.01"}


def call(action_id, param, warmup="/af/USEAFA001M.do"):
    s = requests.Session(); s.headers.update(H)
    try:
        s.get(BASE + "/", timeout=10); time.sleep(0.3)
        s.get(BASE + warmup, timeout=10); time.sleep(0.3)
        payload = {"actionId": action_id, "paramData": json.dumps(param, ensure_ascii=False)}
        r = s.post(BASE + "/action.do", data=payload,
                   headers={**H_XHR, "Referer": BASE + warmup}, timeout=20)
        if not r.text.strip() or r.text.strip()[0] not in ('{', '['):
            return {"_raw": r.text[:200]}
        return r.json()
    except Exception as e:
        return {"_err": str(e)[:100]}


# ── 1) ASIAFA001MR01 - atDVOList 추출 ────────────────────────────────────────
print("=== ASIAFA001MR01 atDVOList 분석 ===")
for param in [
    {"pageIndex": 1, "pageSize": 5, "searchNtstBscId": "stttAll", "srtMthd": "DESC", "srtFeld": "NTST_PMG_DT"},
    {"pageIndex": 1, "pageSize": 5, "searchNtstBscId": "stttAll"},
    {"pageIndex": 1, "pageSize": 5},
    {"pageIndex": 1, "pageSize": 5, "srtMthd": "DESC", "srtFeld": "NTST_PMG_DT"},
]:
    j = call("ASIAFA001MR01", param)
    data = j.get("data") if isinstance(j, dict) else None
    err = j.get("_err", j.get("_raw", "")) if isinstance(j, dict) else str(j)
    if err: print(f"  err: {err[:60]}"); continue
    if data and "ASIAFA001MR01" in data:
        d = data["ASIAFA001MR01"]
        at_list = d.get("atDVOList", [])
        last_idx = d.get("lastIndex", -1)
        total = d.get("totalRecordCount", "?")
        print(f"  param={list(param.keys())}: lastIndex={last_idx} total={total} atDVOList={len(at_list) if at_list else 'null'}")
        if at_list and len(at_list) > 0:
            print(f"  ✅✅ atDVOList[0] keys={list(at_list[0].keys())[:10]}")
            print(f"  샘플: {json.dumps(at_list[0], ensure_ascii=False)[:300]}")
    time.sleep(0.4)

# ── 2) ASIAFB001MR01 (질의회신) - 동일 분석 ─────────────────────────────────
print("\n=== ASIAFB001MR01 (질의회신) ===")
for param in [
    {"pageIndex": 1, "pageSize": 5},
    {"startCount": 1, "viewCount": 5},
    {"pageIndex": 1, "pageSize": 5, "dcmClCd": "001_02"},
    {"pageIndex": 1, "pageSize": 5, "searchKeyword": ""},
]:
    j = call("ASIAFB001MR01", param, warmup="/af/USEAFB001M.do")
    data = j.get("data") if isinstance(j, dict) else None
    err = j.get("_err", j.get("_raw", "")) if isinstance(j, dict) else str(j)
    if err: print(f"  err: {err[:60]}"); continue
    if data and "ASIAFB001MR01" in data:
        d = data["ASIAFB001MR01"]
        if isinstance(d, dict):
            print(f"  param={list(param.keys())}: keys={list(d.keys())[:8]}")
            # 어떤 키에 데이터가 있는지
            for k, v in d.items():
                if isinstance(v, list) and v:
                    print(f"    ✅ key={k}: {len(v)}건! sample_keys={list(v[0].keys())[:6]}")
                elif isinstance(v, (int, str)) and str(v).isdigit() and int(str(v)) > 0:
                    print(f"    ○ {k}={v}")
    time.sleep(0.4)

# ── 3) ASIPDI002PR01 전체 body 필드 확인 ─────────────────────────────────────
print("\n=== ASIPDI002PR01 판례 body 전체 필드 ===")
j = call("ASIPDI002PR01", {
    "collectionName": "precedent,precedent_gr",
    "sortField": "DCM_RGT_DTM/DESC",
    "startCount": 1, "viewCount": 3,
    "dcmClCdCtl": ["001_09"]
}, warmup="/pd/USEPDI001M.do")
data = j.get("data") if isinstance(j, dict) else None
if data and "ASIPDI002PR01" in data:
    d = data["ASIPDI002PR01"]
    if isinstance(d, dict):
        body = d.get("body", [])
        print(f"  body {len(body)}건:")
        if body:
            print(f"  body[0] keys: {list(body[0].keys())}")
            dcm = body[0].get("dcm", {})
            print(f"  dcm keys: {list(dcm.keys())}")
            print(f"  dcm 전체:\n{json.dumps(dcm, ensure_ascii=False, indent=2)}")

# ── 4) 판례 상세 fetch: NTST_FARE_INTC_GRP_SN으로 ────────────────────────────
print("\n=== 판례 상세 actionId 탐색 ===")
# 먼저 list에서 GRP_SN 가져오기
ntst_fare_intc_grp_sn = None
j = call("ASIPDI002PR01", {
    "collectionName": "precedent,precedent_gr",
    "sortField": "DCM_RGT_DTM/DESC",
    "startCount": 1, "viewCount": 1,
    "dcmClCdCtl": ["001_09"]
}, warmup="/pd/USEPDI001M.do")
data = j.get("data") if isinstance(j, dict) else None
if data and "ASIPDI002PR01" in data:
    d = data["ASIPDI002PR01"]
    body = d.get("body", []) if isinstance(d, dict) else []
    if body:
        dcm = body[0].get("dcm", {})
        ntst_fare_intc_grp_sn = dcm.get("NTST_FARE_INTC_GRP_SN")
        ntst_fle_id = dcm.get("NTST_FLE_ID", "")
        print(f"  Sample: NTST_FARE_INTC_GRP_SN={ntst_fare_intc_grp_sn}")
        print(f"  Sample: NTST_FLE_ID={ntst_fle_id}")
        print(f"  All dcm keys: {list(dcm.keys())}")

if ntst_fare_intc_grp_sn:
    # 판례 상세 시도
    for aid in ["ASIPDI001MR01", "ASIPDI003MR01", "ASIPDI001PR01", "ASIPDI003PR01",
                "ASIPDI002MR01", "ASIPDI004MR01"]:
        j2 = call(aid, {"ntstFareIntcGrpSn": ntst_fare_intc_grp_sn}, warmup="/pd/USEPDI001M.do")
        data2 = j2.get("data") if isinstance(j2, dict) else None
        err2 = j2.get("_err", j2.get("_raw", "")) if isinstance(j2, dict) else str(j2)
        if err2: print(f"  {aid}: err={err2[:50]}"); continue
        if data2 and isinstance(data2, dict) and aid in data2:
            d2 = data2[aid]
            if isinstance(d2, dict):
                print(f"  ✅ {aid}: keys={list(d2.keys())[:8]}")
                if d2:
                    # 본문 텍스트 있는지
                    for k, v in d2.items():
                        if isinstance(v, str) and len(v) > 100:
                            print(f"     {k} (len={len(v)}): {v[:100]}")
            elif isinstance(d2, list) and d2:
                print(f"  ✅ {aid}: {len(d2)}건! keys={list(d2[0].keys())[:6]}")
        time.sleep(0.4)

# ── 5) 질의회신 qt 페이지 - 사전답변(001_01) body 샘플 ──────────────────────
print("\n=== 사전답변(001_01) qt 페이지 샘플 ===")
j = call("ASIPDI002PR01", {
    "collectionName": "question,question_gr",
    "sortField": "DCM_RGT_DTM/DESC",
    "startCount": 1, "viewCount": 3,
    "dcmClCdCtl": ["001_01"]
}, warmup="/qt/USEQTJ001M.do")
data = j.get("data") if isinstance(j, dict) else None
if data and "ASIPDI002PR01" in data:
    d = data["ASIPDI002PR01"]
    body = d.get("body", []) if isinstance(d, dict) else []
    print(f"  body {len(body)}건:")
    if body:
        dcm = body[0].get("dcm", {})
        print(f"  dcm keys: {list(dcm.keys())}")
        print(f"  dcm 전체:\n{json.dumps(dcm, ensure_ascii=False, indent=2)}")
