"""
bravo 파이프라인 완료 감지 → court_cases 벡터 DB 재빌드
완료 조건: cache/api_*/issue_logic.json 696개 모두 존재
"""
import sys, os, re, time, subprocess, json
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).parent.parent
CACHE = ROOT / "cache"
API_DIR = ROOT / "cases" / "court_api"
PYTHON = sys.executable
VECTOR_SCRIPT = ROOT / "scripts" / "build_court_vector_db.py"
DONE_MARKER = ROOT / "scripts" / "_pipeline_done.marker"

def make_case_id(api_path):
    raw = json.loads(api_path.read_text(encoding="utf-8"))
    data = raw.get("PrecService", raw)
    court = re.sub(r'[\\/:*?"<>|\s,()（）]', '', data.get("법원명", "법원").strip()) or "법원"
    case_no = re.sub(r'[\\/:*?"<>|\s,()（）]', '', data.get("사건번호", api_path.stem).strip()) or api_path.stem
    return f"{court}_{case_no}"

def count_done():
    return sum(1 for p in API_DIR.glob("*.json")
               if (CACHE / make_case_id(p) / "issue_logic.json").exists())

def total():
    return sum(1 for _ in API_DIR.glob("*.json"))

def ts():
    return datetime.now().strftime("%H:%M:%S")

TOTAL = total()
print(f"[{ts()}] 모니터 시작. 전체 {TOTAL}건 대상.", flush=True)

if DONE_MARKER.exists():
    print(f"[{ts()}] 이미 완료 마커 존재. 종료.", flush=True)
    sys.exit(0)

CHECK_INTERVAL = 60  # 1분마다 체크

while True:
    done = count_done()
    pct = done / TOTAL * 100
    print(f"[{ts()}] {done}/{TOTAL} ({pct:.1f}%)", flush=True)

    if done >= TOTAL:
        print(f"[{ts()}] ✅ 파이프라인 완료! 벡터 DB 재빌드 시작...", flush=True)
        result = subprocess.run(
            [PYTHON, str(VECTOR_SCRIPT), "--refresh-api"],
            cwd=str(ROOT),
            capture_output=True, text=True, encoding="utf-8"
        )
        print(f"[{ts()}] 재빌드 stdout:\n{result.stdout}", flush=True)
        if result.stderr:
            print(f"[{ts()}] 재빌드 stderr:\n{result.stderr}", flush=True)
        if result.returncode == 0:
            print(f"[{ts()}] ✅ 벡터 DB 재빌드 완료!", flush=True)
            DONE_MARKER.write_text("done", encoding="utf-8")
        else:
            print(f"[{ts()}] ❌ 재빌드 실패 (code={result.returncode})", flush=True)
        break

    time.sleep(CHECK_INTERVAL)
