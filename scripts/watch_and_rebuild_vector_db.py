"""
bravo 파이프라인 완료 대기 → court_cases 벡터 DB 자동 재빌드.

완료 조건: 30초 간격으로 폴링, api_ 캐시 수 변화가 없으면 완료로 간주.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

CACHE_DIR  = ROOT / "cache"
TOTAL      = 696
POLL_SEC   = 30
STABLE_CNT = 3  # 연속 N번 동일하면 완료

def count_done() -> int:
    return sum(
        1 for d in CACHE_DIR.glob("api_*")
        if (d / "issue_logic.json").exists()
    )

def main():
    prev  = -1
    stable = 0

    print("=== 파이프라인 완료 대기 중 ===")
    while True:
        done = count_done()
        print(f"  완료: {done}/{TOTAL}", flush=True)

        if done == prev:
            stable += 1
        else:
            stable = 0
            prev = done

        if stable >= STABLE_CNT and done > 0:
            print(f"\n파이프라인 완료 감지 ({done}건). 벡터 DB 재빌드 시작...\n")
            break

        time.sleep(POLL_SEC)

    # 벡터 DB 재빌드
    from scripts.build_court_vector_db import run
    run()
    print("\n court_cases 벡터 DB 재빌드 완료!")


if __name__ == "__main__":
    main()
