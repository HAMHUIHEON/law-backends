import sys, time, datetime
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
cache = Path("cache")
cutoff = time.time() - 180
recent = [(d.name, d.stat().st_mtime) for d in cache.iterdir() if d.is_dir() and d.stat().st_mtime > cutoff]
recent.sort(key=lambda x: x[1], reverse=True)
for name, mtime in recent[:15]:
    tag = "⚠ api_" if name.startswith("api_") else "✅"
    print(f'{tag}  {datetime.datetime.fromtimestamp(mtime).strftime("%H:%M:%S")}  {name}')
