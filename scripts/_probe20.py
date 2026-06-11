"""해석례/해설례/사전답변 collectionName 확정 + 전체 응답 분석"""
import sys, re, json, requests, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
     "Accept-Language": "ko-KR,ko;q=0.9"}
H_XHR = {**H, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*; q=0.01"}


def call(action_id, param, warmup="/is/USEISA001M.do"):
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


# ── 1) 해석례/해설례 collection 탐색 (warmup별) ──────────────────────────────
print("=== 해석례/해설례 collectionName 탐색 ===")

candidate_collections = [
    "interpretation,interpretation_gr",
    "isa,isa_gr", "ela,ela_gr",
    "advisory,advisory_gr", "advisory",
    "ruling,ruling_gr", "decision,decision_gr",
    "commentary,commentary_gr",
    "tax_commentary,tax_commentary_gr",
    "seisa,seisa_gr", "lasc,lasc_gr",
    "interpret_tax,interpret_tax_gr",
]

for warmup, page_name in [
    ("/is/USEISA001M.do", "해석례"),
    ("/el/USEELA001M.do", "해설례"),
]:
    print(f"\n  warmup={page_name}:")
    for cn in candidate_collections:
        j = call("ASIPDI002PR01", {
            "collectionName": cn,
            "sortField": "DCM_RGT_DTM/DESC", "startCount": 1, "viewCount": 5,
        }, warmup=warmup)
        data = j.get("data") if isinstance(j, dict) else None
        err = j.get("_err", j.get("_raw", "")) if isinstance(j, dict) else str(j)
        if err:
            print(f"    err cn={cn}: {err[:50]}"); continue
        if data and isinstance(data, dict) and "ASIPDI002PR01" in data:
            d = data["ASIPDI002PR01"]
            if isinstance(d, dict):
                body = d.get("body", [])
                top = d.get("top", [])
                if body:
                    print(f"    ✅✅ cn={cn}: body={len(body)}건 top={len(top)}")
                    print(f"        샘플: {json.dumps(body[0].get('dcm',{}), ensure_ascii=False)[:200]}")
                else:
                    print(f"    ✅ cn={cn}: body=0건 top={len(top)}")
        time.sleep(0.4)

# ── 2) totalSearch.js 분석 ─────────────────────────────────────────────────
print("\n\n=== totalSearch.js 분석 ===")
s = requests.Session(); s.headers.update(H)
s.get(BASE + "/", timeout=10)
r = s.get(BASE + "/js/common/totalSearch.js?v=1", timeout=15)
totalSearch_text = r.text if r.status_code == 200 else ""
Path("taxlaw/totalSearch.js").write_text(totalSearch_text, encoding="utf-8")
print(f"totalSearch.js ({len(totalSearch_text):,}자)")

collections = re.findall(r"""collectionName['":\s=]+['"]([^'"]+)['"]""", totalSearch_text)
req_calls = re.findall(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", totalSearch_text)
pr_ids = set(re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}PR\d{2}""", totalSearch_text))
print(f"  collectionName: {collections}")
print(f"  Req.doAction: {req_calls}")
print(f"  PR IDs: {sorted(pr_ids)}")
print(f"\n  전체 내용 (처음 5000자):")
print(totalSearch_text[:5000])

# ── 3) ASIAFA001MR01 전체 응답 확인 ─────────────────────────────────────────
print("\n\n=== ASIAFA001MR01 전체 응답 ===")
for warmup in ["/af/USEAFA001M.do", "/qt/USEQTJ001M.do"]:
    j = call("ASIAFA001MR01", {"startCount": 1, "viewCount": 3}, warmup=warmup)
    print(f"warmup={warmup}:")
    print(f"  {json.dumps(j, ensure_ascii=False)[:500]}")
    time.sleep(0.5)

# ── 4) 사전답변 상세 (USEAFA002P.do) 스크립트 분석 ──────────────────────────
print("\n\n=== /af/USEAFA002P.do 분석 ===")
import bs4
s2 = requests.Session(); s2.headers.update(H)
s2.get(BASE + "/", timeout=10)
r2 = s2.get(BASE + "/af/USEAFA002P.do", timeout=15)
soup2 = bs4.BeautifulSoup(r2.text, "html.parser")
for t in soup2.find_all("script"):
    content = t.get_text().strip()
    req_calls2 = re.findall(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", content)
    collections2 = re.findall(r"""collectionName['":\s=]+['"]([^'"]+)['"]""", content)
    if req_calls2 or collections2:
        print(f"  script ({len(content)}자): calls={req_calls2} coll={collections2}")
        for m in re.finditer(r"""Req\.doAction[^;]{0,200}""", content):
            print(f"    ctx: {m.group()[:150]}")
