"""판례 list 필드 완전 확인 + 사전답변/질의회신/해석례 actionId 발견"""
import sys, re, json, requests, time
from pathlib import Path
import bs4
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
     "Accept-Language": "ko-KR,ko;q=0.9"}
H_XHR = {**H, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*; q=0.01"}


def call_fresh(action_id, param, warmup="/pd/USEPDI001M.do"):
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


def get_scripts(page_path, save_as=None):
    s = requests.Session(); s.headers.update(H)
    try:
        s.get(BASE + "/", timeout=10)
        r = s.get(BASE + page_path, timeout=15)
        if save_as:
            Path(f"taxlaw/{save_as}").write_text(r.text, encoding="utf-8")
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        return [t.get_text().strip() for t in soup.find_all("script")
                if not t.get("src") and len(t.get_text().strip()) > 50]
    except Exception as e:
        print(f"  err: {e}")
        return []


# ── 1) 판례 list 필드 전체 확인 ──────────────────────────────────────────────
print("=== ASIPDI002PR01 판례 필드 전체 확인 ===")
j = call_fresh("ASIPDI002PR01", {
    "collectionName": "precedent,precedent_gr",
    "sortField": "DCM_RGT_DTM/DESC",
    "startCount": 1, "viewCount": 5,
    "dcmClCdCtl": ["001_09"]
})
data = j.get("data") if isinstance(j, dict) else None
if data and "ASIPDI002PR01" in data:
    d = data["ASIPDI002PR01"]
    body = d.get("body", []) if isinstance(d, dict) else []
    top = d.get("top", []) if isinstance(d, dict) else []
    print(f"  body {len(body)}건:")
    if body:
        first = body[0]
        print(f"  keys: {list(first.keys())}")
        dcm = first.get("dcm", {})
        print(f"  dcm keys: {list(dcm.keys())}")
        print(f"  dcm 전체: {json.dumps(dcm, ensure_ascii=False)[:600]}")
        print(f"  top: {json.dumps(top, ensure_ascii=False)[:300]}")

# ── 2) 판례 상세 (detail) actionId 탐색 ────────────────────────────────────────
print("\n=== 판례 상세 actionId 탐색 ===")
# /pd/USEPDI002P.do 팝업의 스크립트 분석
popup_scripts = get_scripts("/pd/USEPDI002P.do", "pd_popup.html")
for i, sc in enumerate(popup_scripts):
    req_calls = re.findall(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", sc)
    pr_ids = re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}(?:PR|MR)\d{2}""", sc)
    collection = re.findall(r"""collectionName['":\s=]+['"]([^'"]+)['"]""", sc)
    ntstBsc = re.findall(r"""ntstBscId|ntstGrpSn|fareIntcGrpSn|NTST_FARE""", sc, re.I)
    if req_calls or pr_ids or collection:
        print(f"\n  팝업 스크립트 #{i+1} ({len(sc)}자):")
        print(f"    Req.doAction: {req_calls}")
        print(f"    PR/MR IDs: {pr_ids[:10]}")
        print(f"    collectionName: {collection}")
        print(f"    ntstBsc refs: {ntstBsc[:5]}")
        for m in re.finditer(r"""Req\.doAction[^;]{0,200}""", sc):
            print(f"    ctx: {m.group()[:150]}")

# ── 3) 사전답변 (/af/USEAFA001M.do) 전체 스크립트 분석 ───────────────────────
print("\n=== 사전답변 스크립트 전체 분석 ===")
af_scripts = get_scripts("/af/USEAFA001M.do")
for i, sc in enumerate(af_scripts):
    req_calls = re.findall(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", sc)
    collection = re.findall(r"""collectionName['":\s=]+['"]([^'"]+)['"]""", sc)
    pr_ids = re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}(?:PR|MR)\d{2}""", sc)
    if req_calls or collection:
        print(f"\n  스크립트 #{i+1} ({len(sc)}자):")
        print(f"    Req.doAction: {req_calls}")
        print(f"    collectionName: {collection}")
        print(f"    PR/MR IDs: {pr_ids[:10]}")
        for m in re.finditer(r"""(?:sendReq|Req\.doAction|collectionName)[^;]{0,200}""", sc):
            print(f"    ctx: {m.group()[:150]}")

# ── 4) 질의회신 (/qt/USEQTJ001M.do) 전체 스크립트 분석 ──────────────────────
print("\n=== 질의회신 스크립트 전체 분석 ===")
qt_scripts = get_scripts("/qt/USEQTJ001M.do")
for i, sc in enumerate(qt_scripts):
    req_calls = re.findall(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", sc)
    collection = re.findall(r"""collectionName['":\s=]+['"]([^'"]+)['"]""", sc)
    if req_calls or collection:
        print(f"\n  스크립트 #{i+1} ({len(sc)}자):")
        print(f"    Req.doAction: {req_calls}")
        print(f"    collectionName: {collection}")
        for m in re.finditer(r"""Req\.doAction[^;]{0,200}""", sc):
            print(f"    ctx: {m.group()[:150]}")

# ── 5) 해석례 (/is/USEISA001M.do) 전체 스크립트 분석 ─────────────────────────
print("\n=== 해석례 스크립트 전체 분석 ===")
is_scripts = get_scripts("/is/USEISA001M.do")
all_is_req = []
for i, sc in enumerate(is_scripts):
    req_calls = re.findall(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", sc)
    collection = re.findall(r"""collectionName['":\s=]+['"]([^'"]+)['"]""", sc)
    all_is_req.extend(req_calls)
    if req_calls or collection:
        print(f"\n  스크립트 #{i+1} ({len(sc)}자):")
        print(f"    Req.doAction: {req_calls}")
        print(f"    collectionName: {collection}")
        for m in re.finditer(r"""(?:sendReq|Req\.doAction|collectionName)[^;]{0,200}""", sc):
            print(f"    ctx: {m.group()[:150]}")

# ── 6) ASEISA001MR01 실제 시도 ───────────────────────────────────────────────
print("\n=== ASEISA001MR01 판례 list 시도 (해석례) ===")
for param in [
    {"startCount": 1, "viewCount": 5, "sortField": "FRS_RGT_DTM/DESC"},
    {"pageIndex": 1, "pageSize": 5},
    {"startCount": 1, "viewCount": 5},
    {"schVcb": "", "startCount": 1, "viewCount": 5},
]:
    j = call_fresh("ASEISA001MR01", param, warmup="/is/USEISA001M.do")
    data = j.get("data") if isinstance(j, dict) else None
    err = j.get("_err", j.get("_raw", "")) if isinstance(j, dict) else str(j)
    if err:
        print(f"  err: {err[:60]}")
        continue
    if data and isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and v:
                print(f"  ✅✅ param={param}: key={k} {len(v)}건!")
                print(f"       keys={list(v[0].keys())[:8]}")
                print(f"       샘플: {json.dumps(v[0], ensure_ascii=False)[:200]}")
                break
            elif isinstance(v, dict):
                body = v.get("body", v.get("list", []))
                if body:
                    print(f"  ✅ {k}: body={len(body)}건")
                    break
                else:
                    print(f"  ○ {k}: {json.dumps(v, ensure_ascii=False)[:100]}")
    time.sleep(0.4)

# ── 7) ASIAFA001MR01/02 사전답변 시도 ─────────────────────────────────────────
print("\n=== ASIAFA001MR01/02 사전답변 시도 ===")
for aid in ["ASIAFA001MR01", "ASIAFA001MR02"]:
    for param in [
        {"startCount": 1, "viewCount": 5, "sortField": "FRS_RGT_DTM/DESC"},
        {"pageIndex": 1, "pageSize": 5},
        {"collectionName": "qstn", "startCount": 1, "viewCount": 5},
        {"collectionName": "interpretation", "startCount": 1, "viewCount": 5},
        {},
    ]:
        j = call_fresh(aid, param, warmup="/af/USEAFA001M.do")
        data = j.get("data") if isinstance(j, dict) else None
        err = j.get("_err", j.get("_raw", "")) if isinstance(j, dict) else str(j)
        if err:
            print(f"  {aid}: err={err[:60]}")
            break
        if data and isinstance(data, dict) and aid in data:
            d = data[aid]
            body = d.get("body", d.get("list", []) if isinstance(d, dict) else d) if isinstance(d, dict) else d
            if isinstance(d, list) and d:
                print(f"  ✅✅ {aid} param={param}: {len(d)}건! keys={list(d[0].keys())[:6]}")
                print(f"       샘플: {json.dumps(d[0], ensure_ascii=False)[:200]}")
                break
            elif isinstance(body, list) and body:
                print(f"  ✅ {aid} body={len(body)}건")
                break
            else:
                print(f"  ○ {aid} param={param}: {json.dumps(d, ensure_ascii=False)[:80]}")
        time.sleep(0.3)
