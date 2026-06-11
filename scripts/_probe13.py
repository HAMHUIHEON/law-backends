"""ASISTZ002MR01 / ASISTZ003MR01 집중 탐색 + pd_page 인라인 스크립트 전체 추출"""
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
        s.get(BASE + "/", timeout=10); time.sleep(0.2)
        s.get(BASE + warmup, timeout=10); time.sleep(0.2)
        payload = {"actionId": action_id, "paramData": json.dumps(param, ensure_ascii=False)}
        r = s.post(BASE + "/action.do", data=payload,
                   headers={**H_XHR, "Referer": BASE + warmup}, timeout=15)
        return r.json()
    except Exception as e:
        return {"_err": str(e)[:100]}


# ── 1) pd_page.html 인라인 스크립트 전체 ──────────────────────────────────────
print("=" * 60)
print("=== pd_page.html 인라인 스크립트 전체 추출 ===")
html = Path("taxlaw/pd_page.html").read_text(encoding="utf-8")
soup = bs4.BeautifulSoup(html, "html.parser")
inline_scripts = []
for t in soup.find_all("script"):
    if not t.get("src"):
        content = t.get_text().strip()
        if content and len(content) > 20:
            inline_scripts.append(content)

print(f"  인라인 스크립트 {len(inline_scripts)}개 발견")
for i, sc in enumerate(inline_scripts):
    mr_ids = re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}MR\d{2}""", sc)
    if mr_ids or "actionId" in sc or "Biz." in sc:
        print(f"\n  --- 스크립트 #{i+1} ({len(sc)}자) MR={mr_ids}:")
        print(sc[:3000])

# ── 2) ASISTZ002/003 집중 탐색 ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("=== ASISTZ002MR01 / ASISTZ003MR01 파라미터 탐색 ===")

dcm_codes = ["001_09", "001_01", "001_02", "001_03", "001_05", "001_06", "001_07", "001_08", "001_10", ""]
for aid in ["ASISTZ002MR01", "ASISTZ003MR01"]:
    print(f"\n  -- {aid} --")
    for dcm in dcm_codes:
        for extra in [
            {},
            {"searchNm": ""},
            {"searchNm": "이전가격"},
            {"sortType": "recency"},
            {"sortField": "FRS_RGT_DTM/DESC"},
        ]:
            param = {"pageIndex": 1, "pageSize": 5, "dcmClCd": dcm, **extra}
            j = call_fresh(aid, param)
            data = j.get("data", {}) if isinstance(j, dict) else {}
            err = j.get("_err", "") if isinstance(j, dict) else str(j)
            if err:
                print(f"    err [{dcm}]: {err[:60]}")
                break  # 연결 오류면 다음 dcm으로
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list) and v:
                        print(f"    ✅✅ dcm={dcm} extra={extra}: key={k} {len(v)}건!")
                        print(f"        샘플: {json.dumps(v[0], ensure_ascii=False)[:200]}")
                    elif isinstance(v, dict):
                        cnt = v.get("totalCount") or v.get("total") or v.get("cnt")
                        if cnt:
                            print(f"    ✅  dcm={dcm} extra={extra}: totalCount={cnt}")
                    elif v and str(v) != "{}":
                        print(f"    ○  dcm={dcm}: {k}={str(v)[:60]}")
            time.sleep(0.5)

# ── 3) ASISTA001MR03 (task.js에서) 집중 탐색 ─────────────────────────────────
print("\n=== ASISTA001MR03 집중 탐색 ===")
for param in [
    {"pageIndex": 1, "pageSize": 20},
    {"pageIndex": 1, "pageSize": 5, "dcmClCd": "001_09"},
    {"rltnStttCtl": "", "wnSessionUuid": ""},
    {"rltnStttCtl": "Y", "wnSessionUuid": ""},
    {},
]:
    j = call_fresh("ASISTA001MR03", param)
    data = j.get("data", {}) if isinstance(j, dict) else {}
    err = j.get("_err", "") if isinstance(j, dict) else ""
    if err:
        print(f"  err: {err[:60]}")
        continue
    print(f"  param={param}:")
    print(f"  data={json.dumps(data, ensure_ascii=False)[:300]}")
    time.sleep(0.5)

# ── 4) ASISTZ001MR01의 실제 반환 데이터 전체 확인 ──────────────────────────────
print("\n=== ASISTZ001MR01 실제 반환 데이터 분석 ===")
j = call_fresh("ASISTZ001MR01", {"pageIndex": 1, "pageSize": 5, "searchNm": ""})
data = j.get("data", {}) if isinstance(j, dict) else {}
print(f"  status={j.get('status')} data keys={list(data.keys())[:10]}")
for k, v in data.items():
    if isinstance(v, list):
        print(f"  key={k} ({len(v)}건):")
        if v:
            print(f"    fields={list(v[0].keys())}")
            print(f"    샘플[0]={json.dumps(v[0], ensure_ascii=False)[:300]}")
            if len(v) > 1:
                print(f"    샘플[1]={json.dumps(v[1], ensure_ascii=False)[:200]}")
    elif isinstance(v, dict):
        print(f"  key={k} (dict): {json.dumps(v, ensure_ascii=False)[:200]}")
    else:
        print(f"  key={k}: {str(v)[:100]}")
