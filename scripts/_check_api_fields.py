import sys, json, re
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

api_dir = Path("cases/court_api")
samples = list(api_dir.glob("*.json"))[:5]
for sample in samples:
    raw = json.loads(sample.read_text(encoding="utf-8"))
    data = raw.get("PrecService", raw)
    court = data.get("법원명", "N/A")
    case_no = data.get("사건번호", "N/A")
    date = data.get("선고일자", "N/A")
    print(f"파일: {sample.name} → 법원명={court!r}, 사건번호={case_no!r}, 선고일자={date!r}")
