"""api_ 캐시 중 raw.json 내용이 비어있는 항목 삭제."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
cache_dir = ROOT / "cache"

deleted = 0
kept = 0
for case_dir in sorted(cache_dir.glob("api_*")):
    raw_file = case_dir / "raw.json"
    if not raw_file.exists():
        continue
    raw = json.loads(raw_file.read_text(encoding="utf-8"))
    cleaned = raw.get("cleaned", "")
    if len(cleaned.strip()) < 30:
        shutil.rmtree(case_dir)
        deleted += 1
    else:
        kept += 1

print(f"삭제: {deleted}개 / 유지: {kept}개")
