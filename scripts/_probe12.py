"""판례 actionId 최종 탐색 — Session-per-request (ConnectionResetError 회피)"""
import sys, re, json, requests, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
     "Accept-Language": "ko-KR,ko;q=0.9"}
H_XHR = {**H, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*; q=0.01"}


def new_sess(warmup_path="/pd/USEPDI001M.do"):
    s = requests.Session()
    s.headers.update(H)
    try:
        s.get(BASE + "/", timeout=10)
        time.sleep(0.3)
        s.get(BASE + warmup_path, timeout=10)
        time.sleep(0.3)
    except Exception:
        pass
    return s


def get_js(path, save_name=None):
    s = new_sess("/")
    try:
        r = s.get(BASE + path, timeout=15)
        if r.status_code == 200 and len(r.text) > 50:
            if save_name:
                Path(f"taxlaw/{save_name}").write_text(r.text, encoding="utf-8")
            return r.text
    except Exception as e:
        print(f"  {path}: {e}")
    return ""


def call_action(action_id, param, referer="/pd/USEPDI001M.do"):
    s = new_sess(referer)
    payload = {"actionId": action_id, "paramData": json.dumps(param, ensure_ascii=False)}
    try:
        r = s.post(BASE + "/action.do", data=payload,
                   headers={**H_XHR, "Referer": BASE + referer}, timeout=15)
        return r.json()
    except Exception as e:
        return {"_err": str(e)}


def check_list(action_id, param, label="", referer="/pd/USEPDI001M.do"):
    j = call_action(action_id, param, referer)
    data = j.get("data", {}) if isinstance(j, dict) else {}
    err = j.get("_err") if isinstance(j, dict) else None
    if err:
        print(f"  ✗  [{label or action_id}] err={err[:60]}")
        return False
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and v:
                print(f"  ✅✅ [{label or action_id}] key={k} {len(v)}건!")
                print(f"       샘플: {json.dumps(v[0], ensure_ascii=False)[:200]}")
                return True
            if isinstance(v, dict):
                cnt = v.get("totalCount") or v.get("total") or v.get("cnt")
                if cnt and str(cnt).isdigit() and int(cnt) > 0:
                    print(f"  ✅  [{label or action_id}] totalCount={cnt} keys={list(v.keys())[:6]}")
                    return True
    return False


# ── 1) JS 파일 다운로드 + actionId 추출 ──────────────────────────────────────
print("=" * 60)
print("=== JS 파일 분석 ===")

all_mr_ids = set()
js_files = [
    ("/js/task.js", "task.js"),
    ("/js/common/common_st.js", "common_st.js"),
    ("/js/leftRightFilter.js", "leftRightFilter.js"),
]
for js_path, save_name in js_files:
    text = get_js(js_path, save_name)
    if not text:
        print(f"  {js_path}: 빈 응답")
        continue

    mr_ids = set(re.findall(r"""['"]([A-Z]{2,}[A-Z0-9]{4,}MR\d{2,3})['"]""", text))
    dcm_refs = re.findall(r"""dcmClCd['":\s=,]*['"]([^'"]+)['"]""", text)
    calls = re.findall(r"""callAction\s*\(\s*['"]([^'"]+)['"]""", text)
    action_refs = re.findall(r"""['"]actionId['"]\s*:\s*['"]([^'"]+)['"]""", text)
    all_mr_ids.update(mr_ids)

    print(f"\n{js_path} ({len(text):,}자):")
    print(f"  MR IDs ({len(mr_ids)}): {sorted(mr_ids)}")
    print(f"  dcmClCd refs: {dcm_refs[:10]}")
    print(f"  callAction: {sorted(calls)[:10]}")
    print(f"  actionId refs: {action_refs[:10]}")

    if "task" in js_path:
        print(f"\n  === task.js 내용 (처음 5000자) ===")
        print(text[:5000])

print(f"\n전체 수집 MR IDs ({len(all_mr_ids)}개): {sorted(all_mr_ids)}")

# ── 2) 수집된 actionId 전부 시도 ─────────────────────────────────────────────
if all_mr_ids:
    print("\n=== 수집된 MR IDs 시도 (판례 dcmClCd=001_09) ===")
    for aid in sorted(all_mr_ids):
        check_list(aid, {"pageIndex": 1, "pageSize": 3, "dcmClCd": "001_09"}, aid)
        time.sleep(0.3)

# ── 3) URL 기반 후보 무차별 시도 ─────────────────────────────────────────────
print("\n=== 후보 actionId 무차별 시도 (/pd/USEPDI001M → PDI) ===")
candidates = []
for prefix in ["ASIPDI", "ASIJDG", "ASIPREC", "ASIPAND", "ASIJUD", "ASICRT",
               "ASIPDJ", "ASIPDE", "ASINTL", "ASIPRC", "ASIJDC", "ASIPJD",
               "ASIJDP", "ASISTA", "ASISTPD"]:
    for n in ["001", "002"]:
        for m in ["MR01", "MR02"]:
            candidates.append(f"{prefix}{n}{m}")

for cand in candidates:
    j = call_action(cand, {"pageIndex": 1, "pageSize": 3, "dcmClCd": "001_09"})
    data = j.get("data", {}) if isinstance(j, dict) else {}
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and v:
                print(f"  ✅✅ {cand}: {len(v)}건! sample={json.dumps(v[0], ensure_ascii=False)[:150]}")
            elif isinstance(v, dict) and (v.get("totalCount") or v.get("total") or v.get("cnt")):
                cnt = v.get("totalCount") or v.get("total") or v.get("cnt")
                print(f"  ✅  {cand}: totalCount={cnt}")
    err = j.get("_err", "")
    if err:
        print(f"  ✗ {cand}: {err[:50]}")
    time.sleep(0.25)

# ── 4) pd_page.html에서 actionId 관련 문맥 추출 ──────────────────────────────
print("\n=== pd_page.html 정밀 분석 ===")
html = Path("taxlaw/pd_page.html").read_text(encoding="utf-8")

# actionId 모든 문맥
print("  --- actionId 문맥:")
for m in re.finditer(r""".{0,40}actionId.{0,100}""", html):
    snippet = m.group().strip()
    if "ASI" in snippet or "ASE" in snippet or "callAction" in snippet.lower():
        print(f"    {snippet[:120]}")

# data-* attributes
import bs4
soup = bs4.BeautifulSoup(html, "html.parser")
print("\n  --- data-* action 관련 속성:")
for tag in soup.find_all(True):
    for attr, val in tag.attrs.items():
        if isinstance(val, str):
            if re.match(r"^[A-Z]{3,}[A-Z0-9]{3,}MR\d{2}", val):
                print(f"    tag={tag.name} {attr}={val}")
            elif "action" in attr.lower() and len(val) > 3:
                print(f"    tag={tag.name} {attr}={val[:80]}")

# Handlebars template scripts
print("\n  --- Handlebars 템플릿 내용 (처음 5개):")
for t in soup.find_all("script"):
    t_type = t.get("type", "")
    t_id = t.get("id", "")
    if "handlebars" in t_type.lower() or "template" in t_type.lower() or "x-" in t_type:
        content = t.get_text()[:500]
        mr_in_t = re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}MR\d{2}""", content)
        print(f"    type={t_type} id={t_id} MR={mr_in_t}")
        print(f"    {content[:200]}")

# inline script with callAction or MR
print("\n  --- 인라인 스크립트 MR ID 포함:")
for t in soup.find_all("script"):
    if not t.get("src"):
        content = t.get_text()
        mr_in_t = re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}MR\d{2}""", content)
        if mr_in_t:
            print(f"    MR={mr_in_t} snippet={content[:300]}")
