"""ASIAFA001MR01 키워드 검색 + ASIPDI002PR01 다양한 조합 + 사전답변 HTML 분석"""
import sys, re, json, requests, time
from pathlib import Path
import bs4
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


# ── 1) ASIAFA001MR01 키워드 검색 ─────────────────────────────────────────────
print("=== ASIAFA001MR01 키워드 검색 ===")
for param in [
    {"pageIndex": 1, "pageSize": 5, "searchKeyword": "이전가격"},
    {"pageIndex": 1, "pageSize": 5, "searchCondition": "ttl", "searchKeyword": "이전가격"},
    {"pageIndex": 1, "pageSize": 5, "icldVcbCtl": "이전가격"},
    {"pageIndex": 1, "pageSize": 5, "searchNm": "이전가격"},
    {"startCount": 1, "viewCount": 5, "searchKeyword": "이전가격"},
    {"startCount": 1, "viewCount": 5, "schVcb": "이전가격"},
    {"startCount": 1, "viewCount": 5},  # 빈 검색
    {"pageIndex": 1, "pageSize": 5},     # 빈 검색
]:
    j = call("ASIAFA001MR01", param)
    data = j.get("data") if isinstance(j, dict) else None
    err = j.get("_err", j.get("_raw", "")) if isinstance(j, dict) else str(j)
    if err:
        print(f"  err: {err[:60]}"); continue
    if data and isinstance(data, dict) and "ASIAFA001MR01" in data:
        d = data["ASIAFA001MR01"]
        if isinstance(d, dict):
            last_idx = d.get("lastIndex", -1)
            total = d.get("totalRecordCount", d.get("recordCountPerPage", "?"))
            list_items = d.get("list", d.get("body", d.get("items", [])))
            print(f"  param={list(param.keys())}: lastIndex={last_idx} total={total} list={len(list_items) if list_items else 'n/a'}")
            if list_items and len(list_items) > 0:
                print(f"    ✅ list[0] keys={list(list_items[0].keys())[:6]}")
                print(f"    샘플: {json.dumps(list_items[0], ensure_ascii=False)[:200]}")
            # 전체 구조 키 확인
            if not list_items:
                print(f"    data keys={list(d.keys())}")
    time.sleep(0.4)

# ── 2) 사전답변 HTML에서 실제 데이터 로딩 방식 분석 ────────────────────────────
print("\n=== /af/USEAFA001M.do HTML 내용 분석 ===")
s = requests.Session(); s.headers.update(H)
s.get(BASE + "/", timeout=10)
r_af = s.get(BASE + "/af/USEAFA001M.do", timeout=15)
html_af = r_af.text
Path("taxlaw/af_page.html").write_text(html_af, encoding="utf-8")
print(f"  HTML 크기: {len(html_af):,}자")

# 숨겨진 데이터 찾기
soup_af = bs4.BeautifulSoup(html_af, "html.parser")
# data-* 속성들
print("\n  data-* 속성:")
for tag in soup_af.find_all(True):
    for attr, val in tag.attrs.items():
        if "data-" in attr.lower() and isinstance(val, str) and len(val) > 3:
            if any(x in val for x in ["001_", "AF", "af", "action"]) or re.match(r"[A-Z]{4,}", val):
                print(f"    {tag.name}.{attr}={val[:80]}")

# form과 hidden input
print("\n  form action/hidden:")
for form in soup_af.find_all("form"):
    print(f"  form action={form.get('action', '')} id={form.get('id', '')}")
    for inp in form.find_all("input", type="hidden"):
        if inp.get("name") and inp.get("value"):
            print(f"    hidden: {inp.get('name')}={inp.get('value')[:50]}")

# 페이지 로드 시 실행되는 인라인 스크립트들
print("\n  인라인 스크립트 주요 부분:")
for sc in [t.get_text().strip() for t in soup_af.find_all("script") if not t.get("src") and len(t.get_text().strip()) > 50]:
    if any(x in sc for x in ["doAction", "actionId", "Biz.", "fetch", "ajax", "$.post"]):
        print(f"\n  --- 스크립트 ({len(sc)}자):")
        print(sc[:2000])

# ── 3) ASIPDI002PR01 + interpretation 계열 + keyword ─────────────────────────
print("\n=== ASIPDI002PR01 + interpretation + 검색어 ===")
for cn in ["interpretation,interpretation_gr", "isa,isa_gr", "ela,ela_gr"]:
    for keyword in ["이전가격", "부가가치세", ""]:
        param = {
            "collectionName": cn,
            "sortField": "DCM_RGT_DTM/DESC", "startCount": 1, "viewCount": 5,
        }
        if keyword:
            param["icldVcbCtl"] = keyword
        j = call("ASIPDI002PR01", param, warmup="/is/USEISA001M.do")
        data = j.get("data") if isinstance(j, dict) else None
        err = j.get("_err", j.get("_raw", "")) if isinstance(j, dict) else str(j)
        if err:
            print(f"  err cn={cn} kw={keyword}: {err[:50]}"); continue
        if data and isinstance(data, dict) and "ASIPDI002PR01" in data:
            d = data["ASIPDI002PR01"]
            if isinstance(d, dict):
                body = d.get("body", [])
                top = d.get("top", [])
                print(f"  ✅ cn={cn[:15]} kw={keyword!r}: body={len(body)}건 top={len(top)}")
                if body:
                    print(f"     샘플: {json.dumps(body[0].get('dcm',{}), ensure_ascii=False)[:200]}")
        time.sleep(0.4)

# ── 4) 사전답변 dedicated action 찾기: ASIAFA002MR01, ASIAFB002MR01 등 ────────
print("\n=== 사전답변/질의회신 dedicated action 시도 ===")
for aid in ["ASIAFA002MR01", "ASIAFA001PR01", "ASIAFB002MR01", "ASIAFB001PR01",
            "ASIELA002MR01", "ASIELA001PR01", "ASEISA001PR01", "ASEISA002MR01"]:
    for param in [
        {"pageIndex": 1, "pageSize": 5},
        {"startCount": 1, "viewCount": 5, "sortField": "DCM_RGT_DTM/DESC"},
    ]:
        j = call(aid, param)
        data = j.get("data") if isinstance(j, dict) else None
        err = j.get("_err", j.get("_raw", "")) if isinstance(j, dict) else str(j)
        if err:
            print(f"  {aid}: err={err[:50]}"); break
        if data and isinstance(data, dict) and aid in data:
            d = data[aid]
            if isinstance(d, dict):
                body = d.get("body", d.get("list", []))
                last_idx = d.get("lastIndex", -1)
                if isinstance(body, list) and body:
                    print(f"  ✅✅ {aid}: body={len(body)}건!")
                    print(f"     keys={list(body[0].keys())[:6]}")
                    print(f"     샘플: {json.dumps(body[0], ensure_ascii=False)[:200]}")
                    break
                elif isinstance(d, list) and d:
                    print(f"  ✅✅ {aid}: {len(d)}건!")
                    print(f"     keys={list(d[0].keys())[:6]}")
                    break
                else:
                    print(f"  ○ {aid}: last_idx={last_idx} keys={list(d.keys())[:5]}")
                    break
        time.sleep(0.3)
