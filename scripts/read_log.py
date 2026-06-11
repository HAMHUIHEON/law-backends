import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

p = Path(r"C:\Users\LG\Documents\langchain-kr\29_FINAL\resolve_run2.log")
text = p.read_bytes().decode("utf-8", errors="replace")
lines = text.splitlines()
print(f"총 {len(lines)}줄")
# Find result section
for i, l in enumerate(lines):
    if "결과" in l or "====" in l:
        print(f"L{i}: {l}")
# Print last 20 lines
print("\n=== 마지막 20줄 ===")
for l in lines[-20:]:
    print(l)
