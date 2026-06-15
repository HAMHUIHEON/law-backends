"""
Railway cold-start: 법령 최신 버전 데이터 다운로드 및 추출.
law_latest.tar.gz → /app/law/

환경변수:
  LAW_DOWNLOAD_URL  GitHub Release 다운로드 URL (필수)
  LAW_DIR           법령 데이터 설치 경로 (기본: /app/law)
  LAW_VERSION       버전 태그 (기본: v1)
"""
import os
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

LAW_DIR = Path(os.environ.get("LAW_DIR") or "/app/law")
LAW_DOWNLOAD_URL = os.environ.get("LAW_DOWNLOAD_URL", "")
LAW_VERSION = os.environ.get("LAW_VERSION", "v1")

_version_file = LAW_DIR / ".law_version"


def _is_current() -> bool:
    if _version_file.exists() and _version_file.read_text().strip() == LAW_VERSION:
        return True
    return False


def _download_and_extract(url: str):
    tmp = Path("/tmp/law_latest.tar.gz")
    print(f"[init_law] 다운로드: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as f:
        shutil.copyfileobj(resp, f)
    size_mb = tmp.stat().st_size / 1024 / 1024
    print(f"[init_law] 다운로드 완료 ({size_mb:.1f} MB)")

    if LAW_DIR.exists():
        print(f"[init_law] 기존 {LAW_DIR} 삭제")
        shutil.rmtree(LAW_DIR)
    LAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[init_law] 압축 해제 → {LAW_DIR}")
    with tarfile.open(tmp, "r:gz") as tar:
        members = [m for m in tar.getmembers() if m.name.startswith("law_latest/")]
        for m in members:
            # law_latest/{slug}/... → {slug}/... 로 strip
            m.name = m.name[len("law_latest/"):]
        tar.extractall(LAW_DIR)

    tmp.unlink(missing_ok=True)
    _version_file.write_text(LAW_VERSION)
    print(f"[init_law] 설치 완료: {LAW_DIR} (버전 {LAW_VERSION})")


def main():
    if not LAW_DOWNLOAD_URL:
        print("[init_law] LAW_DOWNLOAD_URL 미설정 — 스킵")
        return

    if _is_current():
        print(f"[init_law] 버전 {LAW_VERSION} 이미 설치됨 — 스킵")
        return

    try:
        _download_and_extract(LAW_DOWNLOAD_URL)
    except Exception as e:
        print(f"[init_law] 오류: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
