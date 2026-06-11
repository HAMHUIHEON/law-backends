#!/usr/bin/env python3
"""
taxlaw.nts.go.kr 구조 정찰 — 숨겨진 JSON API endpoint 탐색.

실행:
    python scripts/probe_taxlaw.py

출력: 발견된 JSON endpoint + 응답 샘플을 probe_results.json에 저장.
"""
import sys, re, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import requests
from bs4 import BeautifulSoup

BASE = "https://taxlaw.nts.go.kr"
OUT  = Path(__file__).parent.parent / "taxlaw" / "probe_results.json"
OUT.parent.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": BASE + "/",
}

# ── 정찰 대상 페이지 ──────────────────────────────────────────────────────────
# 실제 URL은 사이트 메뉴를 열어보고 확인해야 하므로, 일반적인 패턴을 폭넓게 시도.
PAGES_TO_FETCH = [
    ("/",                                   "메인"),
    ("/law/sub/prec/precList.do",           "판례"),
    ("/law/sub/expc/expcList.do",           "세법해설례"),
    ("/law/sub/expc/advnRulingList.do",     "사전답변"),
    ("/law/sub/expc/qnaList.do",            "질의회신"),
    ("/law/sub/expc/taxStdCnslList.do",     "과세기준자문"),
    ("/law/sub/expc/legisExpcList.do",      "법제처해석례"),
    ("/prec/list.do",                       "판례(alt1)"),
    ("/expc/list.do",                       "해설례(alt1)"),
    ("/sub/prec/precList.do",               "판례(alt2)"),
]

# ── 후보 Ajax endpoint ────────────────────────────────────────────────────────
# 한국 정부 사이트 공통 패턴: POST + form-data, 응답 JSON
AJAX_CANDIDATES = [
    # (method, path, payload)
    # 판례
    ("POST", "/law/sub/prec/getPrecList.do",       {"pageIndex":1,"pageSize":10,"searchNm":""}),
    ("POST", "/law/sub/prec/selectPrecList.do",    {"pageIndex":1,"pageSize":10}),
    ("POST", "/prec/getPrecList.do",               {"pageIndex":1,"pageSize":10}),
    ("GET",  "/law/sub/prec/getPrecList.do",       {"pageIndex":1,"pageSize":10}),
    # 사전답변
    ("POST", "/law/sub/expc/getAdvnRulingList.do", {"pageIndex":1,"pageSize":10}),
    ("POST", "/law/sub/expc/selectAdvnList.do",    {"pageIndex":1,"pageSize":10}),
    # 질의회신
    ("POST", "/law/sub/expc/getQnaList.do",        {"pageIndex":1,"pageSize":10}),
    ("POST", "/law/sub/expc/selectQnaList.do",     {"pageIndex":1,"pageSize":10}),
    # 과세기준자문
    ("POST", "/law/sub/expc/getTaxStdCnslList.do", {"pageIndex":1,"pageSize":10}),
    ("POST", "/law/sub/expc/selectTaxStdList.do",  {"pageIndex":1,"pageSize":10}),
    # 법제처 해석례
    ("POST", "/law/sub/expc/getLegisExpcList.do",  {"pageIndex":1,"pageSize":10}),
    ("POST", "/law/sub/expc/selectLegisList.do",   {"pageIndex":1,"pageSize":10}),
    # 통합검색
    ("POST", "/law/sub/srh/getSrhList.do",         {"pageIndex":1,"pageSize":10,"searchNm":"이전가격"}),
    ("POST", "/law/sub/srh/selectSrhList.do",      {"pageIndex":1,"pageSize":10,"searchNm":"이전가격"}),
]


def get(path, params=None):
    try:
        r = requests.get(BASE + path, params=params, headers=HEADERS, timeout=10)
        return r
    except Exception as e:
        return None

def post(path, data):
    try:
        r = requests.post(BASE + path, data=data, headers={
            **HEADERS,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }, timeout=10)
        return r
    except Exception as e:
        return None


def extract_ajax_urls(html: str) -> list[str]:
    """JS 코드에서 .do 경로 추출."""
    urls = re.findall(r"""['"]([^'"]*\.do[^'"]*?)['"]""", html)
    # 파라미터 제거, 중복 제거
    cleaned = list({u.split("?")[0] for u in urls if u.startswith("/")})
    return sorted(cleaned)


def is_json_response(r) -> bool:
    if r is None:
        return False
    ct = r.headers.get("Content-Type", "")
    if "json" in ct:
        return True
    try:
        r.json()
        return True
    except Exception:
        return False


def main():
    results = {"pages": {}, "ajax_hits": [], "discovered_urls": []}

    # ── 1단계: 페이지 HTML 수집 + JS URL 추출 ──────────────────────────────
    print("\n[1] 페이지 HTML 수집")
    all_discovered = set()
    for path, name in PAGES_TO_FETCH:
        r = get(path)
        if r is None or r.status_code != 200:
            print(f"  {name:15s} {path}  → {r.status_code if r else 'ERR'}")
            continue
        ct = r.headers.get("Content-Type", "")
        found_urls = extract_ajax_urls(r.text)
        all_discovered.update(found_urls)
        print(f"  {name:15s} {path}  → {r.status_code}  JS URLs: {len(found_urls)}개")

        # form action 추출
        soup = BeautifulSoup(r.text, "html.parser")
        for form in soup.find_all("form"):
            action = form.get("action", "")
            if action.startswith("/"):
                all_discovered.add(action.split("?")[0])

        results["pages"][path] = {
            "name": name,
            "status": r.status_code,
            "content_type": ct,
            "discovered_urls": found_urls[:30],
        }
        time.sleep(0.5)

    # JS에서 발견한 URL 중 list/get/select 포함된 것만 추가 프로브
    extra = [u for u in all_discovered if any(
        k in u.lower() for k in ["list", "select", "search", "srh", "get"]
    ) and u.endswith(".do")]
    results["discovered_urls"] = sorted(extra)
    print(f"\n  발견된 Ajax 후보 URL: {len(extra)}개")
    for u in extra[:20]:
        print(f"    {u}")

    # ── 2단계: Ajax endpoint 직접 프로브 ──────────────────────────────────
    print("\n[2] Ajax endpoint 프로브")
    hits = []
    all_candidates = list(AJAX_CANDIDATES)
    # JS에서 발견한 URL도 POST로 시도
    for u in extra[:30]:
        all_candidates.append(("POST", u, {"pageIndex":1,"pageSize":10}))

    for method, path, payload in all_candidates:
        r = post(path, payload) if method == "POST" else get(path, payload)
        if r is None:
            continue
        ok = is_json_response(r)
        status = r.status_code
        preview = ""
        if ok and status == 200:
            try:
                j = r.json()
                # 키 목록만 미리보기
                if isinstance(j, dict):
                    preview = str(list(j.keys()))[:100]
                elif isinstance(j, list) and j:
                    preview = str(list(j[0].keys()))[:100] if isinstance(j[0], dict) else str(j[0])[:80]
            except Exception:
                pass
            hit = {"method": method, "path": path, "payload": payload, "keys": preview}
            hits.append(hit)
            print(f"  ✅ {method:4s} {path}")
            print(f"       keys: {preview}")
        else:
            print(f"  ✗  {method:4s} {path}  → {status}  json={ok}")
        time.sleep(0.3)

    results["ajax_hits"] = hits

    # ── 결과 저장 ──────────────────────────────────────────────────────────
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 결과 저장: {OUT}")
    print(f"   JSON 응답 성공 endpoint: {len(hits)}개")
    if hits:
        print("\n[성공한 endpoint]")
        for h in hits:
            print(f"  {h['method']} {h['path']}")
            print(f"    keys: {h['keys']}")


if __name__ == "__main__":
    main()
