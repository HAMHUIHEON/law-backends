"""각 페이지 스크립트에서 collectionName + PR01 완전 추출"""
import sys, re, json, requests, time
from pathlib import Path
import bs4
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
     "Accept-Language": "ko-KR,ko;q=0.9"}
H_XHR = {**H, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*; q=0.01"}


def get_page(page_path, save_name=None):
    s = requests.Session(); s.headers.update(H)
    s.get(BASE + "/", timeout=10)
    r = s.get(BASE + page_path, timeout=15)
    if save_name:
        Path(f"taxlaw/{save_name}").write_text(r.text, encoding="utf-8")
    return r.text


def call_fresh(action_id, param, warmup="/pd/USEPDI001M.do"):
    s = requests.Session(); s.headers.update(H)
    try:
        s.get(BASE + "/", timeout=10); time.sleep(0.3)
        s.get(BASE + warmup, timeout=10); time.sleep(0.3)
        payload = {"actionId": action_id, "paramData": json.dumps(param, ensure_ascii=False)}
        r = s.post(BASE + "/action.do", data=payload,
                   headers={**H_XHR, "Referer": BASE + warmup}, timeout=20)
        if not r.text.strip() or r.text.strip()[0] not in ('{', '['):
            return {"_raw": r.text[:300]}
        return r.json()
    except Exception as e:
        return {"_err": str(e)[:100]}


# ── 1) 각 페이지 스크립트 저장 ─────────────────────────────────────────────
pages = {
    "qt": ("/qt/USEQTJ001M.do", "qt_scripts.txt"),
    "af": ("/af/USEAFA001M.do", "af_scripts.txt"),
    "afb": ("/af/USEAFB001M.do", "afb_scripts.txt"),
    "el": ("/el/USEELA001M.do", "el_scripts.txt"),
    "is": ("/is/USEISA001M.do", "is_scripts.txt"),
}

for key, (page_path, save_name) in pages.items():
    html = get_page(page_path)
    soup = bs4.BeautifulSoup(html, "html.parser")
    inline = [t.get_text().strip() for t in soup.find_all("script")
              if not t.get("src") and len(t.get_text().strip()) > 50]
    combined = "\n\n===SCRIPT_SEP===\n\n".join(inline)
    Path(f"taxlaw/{save_name}").write_text(combined, encoding="utf-8")
    # 주요 정보 추출
    all_text = combined
    collections = re.findall(r"""collectionName['":\s=]+['"]([^'"]+)['"]""", all_text)
    req_calls = re.findall(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", all_text)
    pr_ids = set(re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}PR\d{2}""", all_text))
    mr_ids = set(re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}MR\d{2}""", all_text))
    print(f"\n{key} ({page_path}):")
    print(f"  collectionName: {collections}")
    print(f"  Req.doAction: {req_calls}")
    print(f"  PR IDs: {sorted(pr_ids)}")
    print(f"  MR IDs: {sorted(mr_ids)}")
    # sendReq 근처 context
    for m in re.finditer(r"""(?:ASIPDI002PR01|collectionName)[^;\n]{0,200}""", all_text):
        print(f"  ctx: {m.group()[:150]}")
    time.sleep(0.5)

# ── 2) qt 페이지 main 스크립트 일부 출력 ────────────────────────────────────
print("\n\n=== qt_scripts.txt sendReq 부분 ===")
qt_txt = Path("taxlaw/qt_scripts.txt").read_text(encoding="utf-8") if Path("taxlaw/qt_scripts.txt").exists() else ""
# Biz.sendReq 함수 전체 찾기
m = re.search(r"""Biz\.sendReq\s*=\s*function[^]*?(?=Biz\.\w+\s*=\s*function|\Z)""", qt_txt[:30000])
if m:
    print(m.group()[:2000])
else:
    # Req.doAction("ASIPDI002PR01" 근처 500자
    for m2 in re.finditer(r""".{0,200}ASIPDI002PR01.{0,500}""", qt_txt):
        print(m2.group()[:700])
        break

# ── 3) ASIPDI002PR01 (qt page warmup) + 다른 dcmClCd 시도 ────────────────────
print("\n=== ASIPDI002PR01 + qt warmup + 다양한 dcmClCd ===")
for dcm_list in [["001_01"], ["001_02"], ["001_03"], ["001_01", "001_02", "001_03"]]:
    j = call_fresh("ASIPDI002PR01", {
        "collectionName": "precedent,precedent_gr",
        "sortField": "DCM_RGT_DTM/DESC", "startCount": 1, "viewCount": 5,
        "dcmClCdCtl": dcm_list
    }, warmup="/qt/USEQTJ001M.do")
    data = j.get("data") if isinstance(j, dict) else None
    err = j.get("_err", j.get("_raw", "")) if isinstance(j, dict) else str(j)
    if err:
        print(f"  err dcm={dcm_list}: {err[:60]}"); continue
    if data and isinstance(data, dict) and "ASIPDI002PR01" in data:
        d = data["ASIPDI002PR01"]
        body = d.get("body", []) if isinstance(d, dict) else []
        print(f"  dcm={dcm_list}: body={len(body)}건")
        if body:
            dcm_field = body[0].get("dcm", {}).get("NTST_DCM_CL_CD", "?") or body[0].get("dcm", {}).get("DCM_CL_CD", "?")
            print(f"     dcm_cl_cd={dcm_field} 샘플키={list(body[0].get('dcm',{}).keys())[:5]}")
    time.sleep(0.5)

# ── 4) af page의 main script 전체에서 sendReq 찾기 ────────────────────────────
print("\n=== af_scripts.txt sendReq/doAction ===")
af_txt = Path("taxlaw/af_scripts.txt").read_text(encoding="utf-8") if Path("taxlaw/af_scripts.txt").exists() else ""
# 모든 Req.doAction 컨텍스트
for m in re.finditer(r""".{0,100}Req\.doAction[^;]{0,300}""", af_txt):
    print(f"  {m.group()[:250]}")
# collectionName
for m in re.finditer(r""".{0,50}collectionName.{0,100}""", af_txt):
    print(f"  {m.group()[:150]}")

# ── 5) is_scripts.txt 분석 ────────────────────────────────────────────────────
print("\n=== is_scripts.txt Req.doAction ===")
is_txt = Path("taxlaw/is_scripts.txt").read_text(encoding="utf-8") if Path("taxlaw/is_scripts.txt").exists() else ""
for m in re.finditer(r""".{0,100}Req\.doAction[^;]{0,300}""", is_txt):
    print(f"  {m.group()[:250]}")
for m in re.finditer(r""".{0,50}collectionName.{0,100}""", is_txt):
    print(f"  {m.group()[:150]}")
