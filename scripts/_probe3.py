import sys, re, requests
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
    "Referer": BASE + "/",
}

# ntlis.js - 메인 앱 JS에서 API endpoint 추출
js_files = ["/js/ntlis.js", "/js/common/common.js", "/js/layout.js"]
for js_path in js_files:
    r = requests.get(BASE + js_path, headers=H, timeout=15)
    if r.status_code != 200:
        print(f"{js_path} → {r.status_code}")
        continue
    content = r.text
    print(f"\n=== {js_path} ({len(content):,}자) ===")

    # url: "..." 패턴
    ajax = re.findall(r"""url\s*:\s*['"]([^'"]{3,})['"]""", content)
    for a in sorted(set(ajax))[:30]:
        print(f"  url: {a}")

    # .do URL 전체
    dos = list({d.split("?")[0] for d in re.findall(r"""['"]([^'"]*\.do[^'",\s]{0,50})['"]""", content) if "/" in d})
    for d in sorted(dos)[:40]:
        print(f"  .do: {d}")

    # fetch/axios/$.ajax 패턴
    fetches = re.findall(r"""(?:fetch|ajax|get|post)\s*\(\s*['"]([^'"]+)['"]""", content, re.IGNORECASE)
    for f in sorted(set(fetches))[:20]:
        print(f"  fetch: {f}")
