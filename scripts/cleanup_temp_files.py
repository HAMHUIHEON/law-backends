"""루트 디렉토리 임시 디버그·로그 파일 정리."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

# 삭제 대상 패턴 (루트 직접 파일만)
patterns = [
    r"^debug_.*",
    r"^resolve_.*\.(log|txt)$",
    r"^r2.*\.txt$",
    r"^poll_result\.txt$",
    r"^reset_out\.txt$",
    r"^post_pipeline.*\.(log)$",
    r"^law7_pipeline.*\.(log)$",
    r"^download_missing.*\.(log)$",
    r"^dryrun\d+.*\.txt$",
    r"^history_ingest.*\.(log)$",
    r"^itcl_norm_ingest.*\.(log)$",
]

removed = []
for f in ROOT.iterdir():
    if f.is_file():
        for pat in patterns:
            if re.match(pat, f.name):
                print(f"  삭제: {f.name}")
                f.unlink()
                removed.append(f.name)
                break

print(f"\n총 {len(removed)}개 삭제됨")
