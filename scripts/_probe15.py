"""ASIPDI002PR01 (판례 list) 검증 + 다른 카테고리 PR01 탐색"""
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
        return r.json()
    except Exception as e:
        return {"_err": str(e)[:120]}


def get_inline_scripts(page_path):
    """페이지 HTML에서 인라인 스크립트 추출"""
    s = requests.Session(); s.headers.update(H)
    try:
        s.get(BASE + "/", timeout=10)
        r = s.get(BASE + page_path, timeout=15)
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        scripts = []
        for t in soup.find_all("script"):
            if not t.get("src"):
                content = t.get_text().strip()
                if content and len(content) > 50:
                    scripts.append(content)
        return scripts
    except Exception as e:
        print(f"  get_inline_scripts err: {e}")
        return []


# ── 1) ASIPDI002PR01 기본 시도 ────────────────────────────────────────────────
print("=" * 60)
print("=== ASIPDI002PR01 (판례 list) 검증 ===")
params_to_try = [
    {"startCount": 1, "viewCount": 5, "sortField": "DCM_RGT_DTM/DESC"},
    {"startCount": 1, "viewCount": 5},
    {"pageIndex": 1, "pageSize": 5},
    {"startCount": 1, "viewCount": 5, "sortField": "DCM_RGT_DTM/DESC", "dcmClCd": "001_09"},
    {"startCount": 1, "viewCount": 5, "dcmClCdCtl": ["001_09"]},
    {"startCount": 1, "viewCount": 5, "sortField": "DCM_RGT_DTM/DESC", "dcmClCdCtl": "001_09"},
    {"startCount": 1, "viewCount": 5, "sortField": "DCM_RGT_DTM/DESC", "icldVcbCtl": [], "exclVcbCtl": []},
]
for param in params_to_try:
    j = call_fresh("ASIPDI002PR01", param)
    err = j.get("_err", "") if isinstance(j, dict) else str(j)
    if err:
        print(f"  err: {err[:80]}")
        continue
    data = j.get("data", {}) if isinstance(j, dict) else {}
    status = j.get("status", "?")
    if isinstance(data, dict) and "ASIPDI002PR01" in data:
        d = data["ASIPDI002PR01"]
        body = d.get("body", []) if isinstance(d, dict) else []
        top = d.get("top", []) if isinstance(d, dict) else []
        wnuu = d.get("wnSessionUuid", "") if isinstance(d, dict) else ""
        print(f"  ✅✅ param={param}: body={len(body)}건 top={len(top)} wnUuid={str(wnuu)[:20]}")
        if body:
            print(f"       샘플: {json.dumps(body[0], ensure_ascii=False)[:250]}")
        if top:
            print(f"       top: {json.dumps(top[0], ensure_ascii=False)[:200]}")
    elif status == "SUCCESS":
        print(f"  ✅  param={param}: SUCCESS data_keys={list(data.keys())}")
        print(f"      data={json.dumps(data, ensure_ascii=False)[:200]}")
    else:
        print(f"  ✗  param={param}: {status} {str(data)[:100]}")
    time.sleep(0.5)

# ── 2) 다른 카테고리 페이지 인라인 스크립트에서 PR01 탐색 ──────────────────────
print("\n" + "=" * 60)
print("=== 카테고리 페이지별 PR01 actionId 탐색 ===")

pages = [
    ("/af/USEAFA001M.do", "사전답변"),
    ("/qt/USEQTJ001M.do", "질의회신"),
    ("/el/USEELA001M.do", "해설례"),
    ("/is/USEISA001M.do", "해석례"),
]

for page_path, name in pages:
    print(f"\n  {name} ({page_path})")
    scripts = get_inline_scripts(page_path)
    all_pr_ids = set()
    all_mr_ids = set()
    for sc in scripts:
        pr_ids = re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}PR\d{2}""", sc)
        mr_ids = re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}MR\d{2}""", sc)
        all_pr_ids.update(pr_ids)
        all_mr_ids.update(mr_ids)
        # sendReq 패턴 찾기
        for m in re.finditer(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", sc):
            all_pr_ids.add(m.group(1))
    print(f"    PR IDs: {sorted(all_pr_ids)}")
    print(f"    MR IDs: {sorted(all_mr_ids)}")

    # 유망한 PR actionId 즉시 시도
    for aid in sorted(all_pr_ids):
        j = call_fresh(aid, {"startCount": 1, "viewCount": 5, "sortField": "FRS_RGT_DTM/DESC"},
                       warmup=page_path)
        data = j.get("data", {}) if isinstance(j, dict) else {}
        err = j.get("_err", "")
        if err:
            print(f"    {aid}: err={err[:50]}")
            continue
        if isinstance(data, dict) and aid in data:
            d = data[aid]
            body = d.get("body", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])
            print(f"    ✅ {aid}: body={len(body)}건")
            if body:
                print(f"       샘플: {json.dumps(body[0] if isinstance(body[0], dict) else body[0], ensure_ascii=False)[:200]}")
        elif j.get("status") == "SUCCESS":
            print(f"    ✅ {aid}: SUCCESS data_keys={list(data.keys())}")
        time.sleep(0.5)
    time.sleep(1.0)
