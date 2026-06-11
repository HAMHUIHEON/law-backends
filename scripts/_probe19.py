"""af/el/is 페이지 로드 JS 파일에서 collectionName 찾기"""
import sys, re, json, requests, time
from pathlib import Path
import bs4
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
     "Accept-Language": "ko-KR,ko;q=0.9"}
H_XHR = {**H, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*; q=0.01"}


def get_page_js_files(page_path):
    s = requests.Session(); s.headers.update(H)
    s.get(BASE + "/", timeout=10)
    r = s.get(BASE + page_path, timeout=15)
    soup = bs4.BeautifulSoup(r.text, "html.parser")
    scripts = []
    for t in soup.find_all("script", src=True):
        src = t.get("src", "")
        if src and not any(x in src for x in ["vendor", "jquery", "handlebars"]):
            scripts.append(src)
    return scripts


def fetch_js(path):
    s = requests.Session(); s.headers.update(H)
    try:
        s.get(BASE + "/", timeout=10)
        r = s.get(BASE + path, timeout=15)
        if r.status_code == 200 and len(r.text) > 50:
            return r.text
    except Exception:
        pass
    return ""


def call_fresh(action_id, param, warmup="/af/USEAFA001M.do"):
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


# ── 1) 각 페이지 로드 JS 파일 목록 ─────────────────────────────────────────
print("=== 각 페이지 로드 JS 파일 ===")
pages_to_check = [
    ("/af/USEAFA001M.do", "사전답변"),
    ("/af/USEAFB001M.do", "질의회신B"),
    ("/el/USEELA001M.do", "해설례"),
    ("/is/USEISA001M.do", "해석례"),
]
for page_path, name in pages_to_check:
    js_files = get_page_js_files(page_path)
    print(f"\n{name} ({page_path}):")
    for js in js_files:
        print(f"  {js}")
    time.sleep(0.5)

# ── 2) 사전답변/해석례 페이지별 task.js 유사 파일에서 collectionName ─────────
print("\n\n=== 사전답변/해석례 페이지별 JS 분석 ===")
# af/el/is 페이지는 공통 task.js를 쓰지만 파라미터가 다를 수 있음
# 실제 af 페이지의 JS 파일들을 다운로드해서 분석
pages_js = {
    "af": "/af/USEAFA001M.do",
    "el": "/el/USEELA001M.do",
    "is": "/is/USEISA001M.do",
}
for key, page_path in pages_js.items():
    js_files = get_page_js_files(page_path)
    print(f"\n{key} 페이지의 JS 파일:")
    for js_path in js_files:
        text = fetch_js(js_path)
        if not text:
            print(f"  {js_path}: 빈 응답")
            continue
        collections = re.findall(r"""collectionName['":\s=]+['"]([^'"]+)['"]""", text)
        req_calls = re.findall(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", text)
        pr_ids = set(re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}PR\d{2}""", text))
        if collections or req_calls or pr_ids:
            print(f"  {js_path} ({len(text):,}자):")
            print(f"    collectionName: {collections}")
            print(f"    Req.doAction: {req_calls}")
            print(f"    PR IDs: {sorted(pr_ids)}")
        time.sleep(0.2)
    time.sleep(0.5)

# ── 3) ASIPDI002PR01 + question,question_gr + dcmClCd 시도 ────────────────────
print("\n\n=== ASIPDI002PR01 + question,question_gr 시도 ===")
for dcm_list in [
    ["001_01"],          # 사전답변
    ["001_02"],          # 질의회신
    ["001_03"],          # 과세기준자문
    ["001_01", "001_02", "001_03"],  # 전체
]:
    j = call_fresh("ASIPDI002PR01", {
        "collectionName": "question,question_gr",
        "sortField": "DCM_RGT_DTM/DESC", "startCount": 1, "viewCount": 5,
        "dcmClCdCtl": dcm_list
    }, warmup="/qt/USEQTJ001M.do")
    data = j.get("data") if isinstance(j, dict) else None
    err = j.get("_err", j.get("_raw", "")) if isinstance(j, dict) else str(j)
    if err:
        print(f"  err dcm={dcm_list}: {err[:60]}"); continue
    if data and isinstance(data, dict) and "ASIPDI002PR01" in data:
        d = data["ASIPDI002PR01"]
        if isinstance(d, dict):
            body = d.get("body", [])
            top = d.get("top", [])
            print(f"  dcm={dcm_list}: body={len(body)}건 top={len(top)}")
            if body:
                print(f"    dcm_keys={list(body[0].get('dcm',{}).keys())[:8]}")
                print(f"    샘플: {json.dumps(body[0].get('dcm',{}), ensure_ascii=False)[:200]}")
    else:
        print(f"  dcm={dcm_list}: {str(data)[:100]}")
    time.sleep(0.5)

# ── 4) qt 페이지 collectionName 다시 확인 ─────────────────────────────────────
print("\n=== qt_scripts collectionName 컨텍스트 ===")
qt_txt = Path("taxlaw/qt_scripts.txt").read_text(encoding="utf-8") if Path("taxlaw/qt_scripts.txt").exists() else ""
for m in re.finditer(r""".{0,100}collectionName.{0,100}""", qt_txt):
    print(f"  {m.group()[:200]}")

# ── 5) 해석례 ASEISA001MR01 전체 응답 확인 ─────────────────────────────────────
print("\n=== ASEISA001MR01 전체 응답 ===")
j = call_fresh("ASEISA001MR01", {"startCount": 1, "viewCount": 5, "sortField": "FRS_RGT_DTM/DESC"},
               warmup="/is/USEISA001M.do")
print(f"  응답: {json.dumps(j, ensure_ascii=False)[:500]}")

# ── 6) 추가 추측 collectionName 시도 ─────────────────────────────────────────
print("\n=== 다양한 collectionName 추측 ===")
collection_guesses = [
    "advice,advice_gr", "advice", "ruling", "qstn,qstn_gr", "qstn",
    "precedent", "precedent_gr", "interpret", "interpretation",
    "commentary", "explanation", "isa,isa_gr", "ela,ela_gr",
    "interpretation,interpretation_gr",
]
for cn in collection_guesses:
    j = call_fresh("ASIPDI002PR01", {
        "collectionName": cn,
        "sortField": "DCM_RGT_DTM/DESC", "startCount": 1, "viewCount": 5,
    }, warmup="/is/USEISA001M.do")
    data = j.get("data") if isinstance(j, dict) else None
    err = j.get("_err", j.get("_raw", "")) if isinstance(j, dict) else str(j)
    if err:
        print(f"  err cn={cn}: {err[:50]}"); continue
    if data and isinstance(data, dict) and "ASIPDI002PR01" in data:
        d = data["ASIPDI002PR01"]
        if isinstance(d, dict):
            body = d.get("body", [])
            top = d.get("top", [])
            print(f"  ✅ cn={cn}: body={len(body)}건 top={len(top)}")
            if body:
                print(f"     샘플: {json.dumps(body[0].get('dcm',{}), ensure_ascii=False)[:200]}")
        else:
            print(f"  ○ cn={cn}: {str(d)[:100]}")
    time.sleep(0.5)
