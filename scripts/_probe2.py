import sys, re, json, requests, time
from bs4 import BeautifulSoup
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": BASE + "/",
}

targets = ["/prec/list.do", "/expc/list.do"]
for url in targets:
    r = requests.get(BASE + url, headers=H, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    print(f"\n=== {url} ===")

    # form actions
    for f in soup.find_all("form"):
        print(f"  FORM action={f.get('action')} id={f.get('id')}")

    # external JS
    for s in soup.find_all("script", src=True):
        src = s.get("src", "")
        if src and ".do" not in src:
            print(f"  SCRIPT {src}")

    # inline JS 분석
    inline = " ".join(s.string or "" for s in soup.find_all("script") if s.string)
    ajax_urls = re.findall(r"""url\s*:\s*['"]([^'"]+)['"]""", inline)
    for a in ajax_urls[:15]:
        print(f"  AJAX url: {a}")

    do_urls = list({d.split("?")[0] for d in re.findall(r"""['"]([^'"]*\.do[^'"]*?)['"]""", inline) if "/" in d})
    for d in sorted(do_urls)[:30]:
        print(f"  .do: {d}")

    time.sleep(0.5)
