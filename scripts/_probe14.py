"""pd_page 스크립트 전체 + wnSessionUuid 기반 탐색"""
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


# ── 1) pd_page.html 스크립트 #1 전체 출력 ────────────────────────────────────
print("=== pd_page.html 스크립트 #1 전체 (23727자) ===")
html = Path("taxlaw/pd_page.html").read_text(encoding="utf-8")
soup = bs4.BeautifulSoup(html, "html.parser")
inline_scripts = []
for t in soup.find_all("script"):
    if not t.get("src"):
        content = t.get_text().strip()
        if content and len(content) > 20:
            inline_scripts.append(content)

# 스크립트 #1 전체 저장
Path("taxlaw/pd_script1.js").write_text(inline_scripts[0], encoding="utf-8")
print(f"pd_script1.js 저장 ({len(inline_scripts[0])}자)")
print("  ==> 핵심 검색 부분:")
# Biz.search / Biz.getList 등 찾기
for m in re.finditer(r"""Biz\.\w+\s*=\s*function[^{]*\{""", inline_scripts[0]):
    print(f"  함수: {m.group()[:80]}")
# actionId 사용 컨텍스트 전체
for m in re.finditer(r"""(ASISTZ|ASISTA|actionId)[^;]{0,200}""", inline_scripts[0]):
    print(f"  ctx: {m.group()[:200]}")

# ── 2) 스크립트 #6 전체도 저장 ───────────────────────────────────────────────
Path("taxlaw/pd_script6.js").write_text(inline_scripts[5], encoding="utf-8")
print(f"\npd_script6.js 저장 ({len(inline_scripts[5])}자)")
for m in re.finditer(r"""(ASISTZ|ASISTA|actionId)[^;]{0,200}""", inline_scripts[5]):
    print(f"  ctx: {m.group()[:200]}")

# ── 3) wnSessionUuid로 판례 list 시도 ─────────────────────────────────────────
print("\n=== wnSessionUuid 기반 판례 list 탐색 ===")
# 먼저 ASISTA001MR03으로 wnSessionUuid 획득
j_meta = call_fresh("ASISTA001MR03", {})
uuid = j_meta.get("data", {}).get("ASISTA001MR03", {}).get("wnSessionUuid", "")
print(f"  wnSessionUuid: {uuid}")

# ASISTZ001MR01에 dcmClCd=001_09로 시도
print("\n  ASISTZ001MR01 + dcmClCd=001_09:")
j = call_fresh("ASISTZ001MR01", {"pageIndex": 1, "pageSize": 5, "dcmClCd": "001_09", "wnSessionUuid": uuid})
print(f"  {json.dumps(j.get('data', {}), ensure_ascii=False)[:300]}")

# 전체 dcm 코드 없이, wnSessionUuid만
print("\n  ASISTZ001MR01 + wnSessionUuid만:")
j2 = call_fresh("ASISTZ001MR01", {"wnSessionUuid": uuid, "pageIndex": 1, "pageSize": 5})
data2 = j2.get("data", {}).get("ASISTZ001MR01", [])
print(f"  {len(data2)}건: {json.dumps(data2[:2], ensure_ascii=False)[:300]}")

# ── 4) boot.js / ntlis.js에서 실제 list call 찾기 ─────────────────────────────
print("\n=== boot.js 분석 ===")
s = requests.Session(); s.headers.update(H)
s.get(BASE + "/", timeout=10)
r = s.get(BASE + "/js/common/boot.js", timeout=10)
boot_text = r.text if r.status_code == 200 else ""
Path("taxlaw/boot.js").write_text(boot_text, encoding="utf-8")
print(f"  boot.js ({len(boot_text)}자)")
mr_boot = re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}MR\d{2}""", boot_text)
print(f"  MR IDs: {mr_boot}")
# Req.doAction 패턴
req_calls = re.findall(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", boot_text)
print(f"  Req.doAction calls: {req_calls}")
print(boot_text[:3000])

# ── 5) ntlis.js Req.doAction 패턴 전체 ────────────────────────────────────────
print("\n=== ntlis.js Req.doAction 패턴 ===")
ntlis = Path("taxlaw/ntlis.js").read_text(encoding="utf-8") if Path("taxlaw/ntlis.js").exists() else ""
if not ntlis:
    r2 = requests.Session(); r2 = requests.get(BASE + "/js/ntlis.js", headers=H, timeout=10)
    ntlis = r2.text
    Path("taxlaw/ntlis.js").write_text(ntlis, encoding="utf-8")
mr_ntlis = re.findall(r"""[A-Z]{2,}[A-Z0-9]{4,}MR\d{2}""", ntlis)
print(f"  MR IDs: {sorted(set(mr_ntlis))}")
req_ntlis = re.findall(r"""Req\.doAction\s*\(\s*['"]([^'"]+)['"]""", ntlis)
print(f"  Req.doAction calls: {req_ntlis}")
# actionId 문맥
for m in re.finditer(r"""actionId[^;]{0,150}""", ntlis):
    print(f"  actionId ctx: {m.group()[:120]}")
# 처음 4000자
print(ntlis[:4000])

# ── 6) ASISTZ001MR01 다른 파라미터 조합 ──────────────────────────────────────
print("\n=== ASISTZ001MR01 판례 dcmClCd 파라미터 변형 ===")
base_params = [
    {"pageIndex": 1, "pageSize": 5, "dcmClCd": "001_09"},
    {"pageIndex": 1, "pageSize": 5, "tlawClCd": "001_09"},
    {"pageIndex": 1, "pageSize": 5, "ntstSysClCd": "01"},
    {"pageIndex": 1, "pageSize": 5, "searchType": "prts"},   # pd 페이지에서 prts = 판례
    {"pageIndex": 1, "pageSize": 5, "dcmType": "prts"},
    {"pageIndex": 1, "pageSize": 5, "schVcb": "", "dcmClCd": "001_09"},
    {"pageIndex": 1, "pageSize": 5, "icldVcbCtl": "", "dcmClCd": "001_09"},
    {"pageIndex": 1, "pageSize": 5, "searchNm": "", "dcmClCd": "001_09"},
    {"viewCount": 5, "startCount": 1, "dcmClCd": "001_09"},   # Biz.viewCount, Biz.startCount
    {"viewCount": 5, "startCount": 1, "sortField": "DCM_RGT_DTM/DESC", "dcmClCd": "001_09"},
]
for param in base_params:
    j = call_fresh("ASISTZ001MR01", param)
    data = j.get("data", {}) if isinstance(j, dict) else {}
    err = j.get("_err", "")
    if err:
        print(f"  err: {err[:60]}")
        continue
    tz = data.get("ASISTZ001MR01", [])
    if isinstance(tz, list):
        print(f"  param={param}: {len(tz)}건 → {json.dumps(tz[0], ensure_ascii=False)[:100] if tz else '없음'}")
    else:
        print(f"  param={param}: {str(data)[:100]}")
    time.sleep(0.4)
