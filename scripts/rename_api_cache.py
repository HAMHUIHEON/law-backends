"""
기존 cache/api_* 디렉토리를 {법원명}_{사건번호} 형식으로 일괄 이름 변경
실행 전 dry-run으로 확인 가능: python rename_api_cache.py --dry-run
"""
import sys, json, re, shutil
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
CACHE = ROOT / "cache"
API_DIR = ROOT / "cases" / "court_api"
TMP_DIR = ROOT / "cases" / "_tmp_txt"


def make_case_id(api_path: Path) -> str:
    raw = json.loads(api_path.read_text(encoding="utf-8"))
    data = raw.get("PrecService", raw)
    court = re.sub(r'[\\/:*?"<>|\s,()（）]', '', data.get("법원명", "법원").strip())
    case_no = re.sub(r'[\\/:*?"<>|\s,()（）]', '', data.get("사건번호", api_path.stem).strip())
    if not court:
        court = "법원"
    if not case_no:
        case_no = api_path.stem
    return f"{court}_{case_no}"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_files = {f.stem: f for f in API_DIR.glob("*.json")}
    renamed = 0
    skipped = 0
    conflicts = 0

    for stem, api_path in sorted(api_files.items()):
        old_cache = CACHE / f"api_{stem}"
        if not old_cache.exists():
            continue

        new_id = make_case_id(api_path)
        new_cache = CACHE / new_id

        if new_cache.exists() and new_cache != old_cache:
            print(f"  [중복삭제] {old_cache.name} → {new_id} (더 완성된 버전 존재, api_ 삭제)")
            conflicts += 1
            if not args.dry_run:
                shutil.rmtree(old_cache)
                # tmp txt도 삭제
                old_txt = TMP_DIR / f"api_{stem}.txt"
                if old_txt.exists():
                    old_txt.unlink()
            continue

        if old_cache == new_cache:
            skipped += 1
            continue

        print(f"  {old_cache.name} → {new_id}")
        if not args.dry_run:
            old_cache.rename(new_cache)

        # _tmp_txt 도 이름 변경
        old_txt = TMP_DIR / f"api_{stem}.txt"
        if old_txt.exists():
            new_txt = TMP_DIR / f"{new_id}.txt"
            if not args.dry_run:
                old_txt.rename(new_txt)

        renamed += 1

    mode = "DRY-RUN" if args.dry_run else "완료"
    print(f"\n[{mode}] 변경={renamed}, 스킵={skipped}, 충돌={conflicts}")


if __name__ == "__main__":
    main()
