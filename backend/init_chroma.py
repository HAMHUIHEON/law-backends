"""Railway cold-start: Chroma DB download if not present. Pure Python — no bash needed."""
import os
import subprocess
import sys
import zipfile
from pathlib import Path

CHROMA_DIR = Path(os.environ.get("CHROMA_DIR", "/app/chroma"))
CHROMA_URL = os.environ.get("CHROMA_DOWNLOAD_URL", "")

if (CHROMA_DIR / "chroma.sqlite3").exists():
    print("[init_chroma] Chroma exists — skipping download")
    sys.exit(0)

if not CHROMA_URL:
    print("[init_chroma] WARNING: CHROMA_DOWNLOAD_URL not set. Starting without Chroma.")
    sys.exit(0)

print(f"[init_chroma] Chroma 없음 — 다운로드 시작: {CHROMA_URL}")
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

zip_path = Path("/tmp/chroma_data.zip")
subprocess.run(
    ["curl", "-L", "--retry", "3", "--retry-delay", "5", "-o", str(zip_path), CHROMA_URL],
    check=True,
)

print(f"[init_chroma] 압축 해제 → {CHROMA_DIR}")
with zipfile.ZipFile(zip_path) as zf:
    for member in zf.infolist():
        member.filename = member.filename.replace("\\", "/")
        zf.extract(member, str(CHROMA_DIR))

zip_path.unlink(missing_ok=True)
print("[init_chroma] Chroma 준비 완료")
