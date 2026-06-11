"""ASIPDI002PR01 + collectionName 으로 판례 list 완성 + af/is 페이지 스크립트 분석"""
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
        # raw 응답 확인
        if not r.text.strip() or r.text.strip()[0] not in ('{', '['):
            print(f"  [raw] status={r.status_code} first200={repr(r.text[:200])}")
            return {"_raw": r.text[:200]}
        return r.json()
    except Exception as e:
        return {"_err": str(e)[:120]}


def get_page_scripts(page_path, save_as=None):
    s = requests.Session(); s.headers.update(H)
    try:
        s.get(BASE + "/", timeout=10)
        r = s.get(BASE + page_path, timeout=15)
        if save_as:
            Path(f"taxlaw/{save_as}").write_text(r.text, encoding="utf-8")
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        scripts = [t.get_text().strip() for t in soup.find_all("script")
                   if not t.get("src") and len(t.get_text().strip()) > 50]
        return scripts, r.text
    except Exception as e:
        print(f"  err: {e}")
        return [], ""


# ── 1) ASIPDI002PR01 with collectionName ─────────────────────────────────────
print("=" * 60)
print("=== ASIPDI002PR01 + collectionName 시도 ===")

dcm_all = ["001_05", "001_06", "001_07", "001_08", "001_09", "001_10"]

params_list = [
    # 전체 (all)
    {"collectionName": "precedent,precedent_gr",
     "sortField": "DCM_RGT_DTM/DESC", "startCount": 1, "viewCount": 10,
     "dcmClCdCtl": dcm_all},
    # 판례만
    {"collectionName": "precedent,precedent_gr",
     "sortField": "DCM_RGT_DTM/DESC", "startCount": 1, "viewCount": 10,
     "dcmClCdCtl": ["001_09"]},
    # collectionName만
    {"collectionName": "precedent,precedent_gr",
     "sortField": "DCM_RGT_DTM/DESC", "startCount": 1, "viewCount": 10},
    # pageIndex/pageSize 방식
    {"collectionName": "precedent,precedent_gr",
     "sortField": "DCM_RGT_DTM/DESC", "pageIndex": 1, "pageSize": 10,
     "dcmClCdCtl": ["001_09"]},
]

for param in params_list:
    j = call_fresh("ASIPDI002PR01", param)
    raw = j.get("_raw", "") if isinstance(j, dict) else ""
    err = j.get("_err", "") if isinstance(j, dict) else ""
    if raw or err:
        print(f"  ✗ param={list(param.keys())}: raw/err={raw or err}")
        continue
    data = j.get("data", {}) if isinstance(j, dict) else {}
    status = j.get("status", "?")
    if "ASIPDI002PR01" in data:
        d = data["ASIPDI002PR01"]
        body = d.get("body", []) if isinstance(d, dict) else []
        top = d.get("top", []) if isinstance(d, dict) else []
        print(f"  ✅✅ param={list(param.keys())} body={len(body)}건 top={len(top)}")
        if body:
            print(f"       샘플: {json.dumps(body[0], ensure_ascii=False)[:300]}")
    else:
        print(f"  ○  {status}: {str(data)[:150]}")
    time.sleep(0.5)

# ── 2) 사전답변(/af/USEAFA001M.do) 인라인 스크립트 상세 분석 ────────────────────
print("\n" + "=" * 60)
print("=== 사전답변 페이지 스크립트 분석 ===")
af_scripts, af_html = get_page_scripts("/af/USEAFA001M.do", "af_page.html")
Path("taxlaw/af_script1.js").write_text(af_scripts[0] if af_scripts else "", encoding="utf-8")

print(f"  스크립트 {len(af_scripts)}개")
for i, sc in enumerate(af_scripts):
    pr_ids = re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}(?:PR|MR)\d{2}""", sc)
    req_calls = re.findall(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", sc)
    collection = re.findall(r"""collectionName['":\s=]+['"]([^'"]+)['"]""", sc)
    if pr_ids or req_calls or collection:
        print(f"\n  스크립트 #{i+1} ({len(sc)}자):")
        print(f"    PR/MR IDs: {pr_ids}")
        print(f"    Req.doAction: {req_calls}")
        print(f"    collectionName: {collection}")
        # sendReq 함수 찾기
        for m in re.finditer(r"""(?:sendReq|doAction|collectionName)[^;]{0,200}""", sc):
            print(f"    ctx: {m.group()[:150]}")

# ── 3) 해석례(/is/USEISA001M.do) 스크립트 분석 ───────────────────────────────
print("\n=== 해석례 페이지 스크립트 분석 ===")
is_scripts, is_html = get_page_scripts("/is/USEISA001M.do", "is_page.html")
Path("taxlaw/is_script1.js").write_text(is_scripts[0] if is_scripts else "", encoding="utf-8")

for i, sc in enumerate(is_scripts):
    req_calls = re.findall(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", sc)
    collection = re.findall(r"""collectionName['":\s=]+['"]([^'"]+)['"]""", sc)
    pr_ids = re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}(?:PR|MR)\d{2}""", sc)
    if req_calls or collection or (pr_ids and len(pr_ids) > 2):
        print(f"\n  스크립트 #{i+1} ({len(sc)}자):")
        print(f"    Req.doAction: {req_calls}")
        print(f"    collectionName: {collection}")
        for m in re.finditer(r"""Req\.doAction[^;]{0,200}""", sc):
            print(f"    doAction ctx: {m.group()[:150]}")

# ── 4) ASEISA001MR01 (해석례 list) 상세 분석 ─────────────────────────────────
print("\n=== ASEISA001MR01/02/03 (해석례) 상세 분석 ===")
for aid in ["ASEISA001MR01", "ASEISA001MR02", "ASEISA001MR03"]:
    for param in [
        {"pageIndex": 1, "pageSize": 5},
        {"startCount": 1, "viewCount": 5, "sortField": "FRS_RGT_DTM/DESC"},
        {"pageIndex": 1, "pageSize": 5, "schVcb": "이전가격"},
    ]:
        j = call_fresh(aid, param, warmup="/is/USEISA001M.do")
        data = j.get("data", {}) if isinstance(j, dict) else {}
        err = j.get("_err", j.get("_raw", "")) if isinstance(j, dict) else str(j)
        if err:
            print(f"  {aid}: err={err[:60]}")
            break
        if aid in data:
            d = data[aid]
            if isinstance(d, list) and d:
                print(f"  ✅✅ {aid} param={param}: {len(d)}건! keys={list(d[0].keys())[:6]}")
                print(f"       샘플: {json.dumps(d[0], ensure_ascii=False)[:200]}")
                break
            elif isinstance(d, dict):
                body = d.get("body", d.get("list", []))
                if body:
                    print(f"  ✅ {aid} param={param}: body={len(body)}건")
                    break
                else:
                    print(f"  ○ {aid} param={param}: {str(d)[:80]}")
        elif j.get("status") == "SUCCESS":
            print(f"  ✅ {aid} param={param}: SUCCESS data={str(data)[:80]}")
        time.sleep(0.4)
