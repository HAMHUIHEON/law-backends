"""
다운로드된 법령 JSON 파일에서 버전 인덱스만 빌드합니다.
다운로드 없이 인덱스만 재생성할 때 사용.

실행:
  python build_law_index_only.py
  python build_law_index_only.py --law 국세기본법
"""

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent
LAW_DIR = ROOT / "law"

SLUGS = {
    "국세기본법":       "gukse_basic",
    "국세징수법":       "gukse_collection",
    "법인세법":         "corporate_tax",
    "소득세법":         "income_tax",
    "부가가치세법":     "vat",
    "조세범처벌법":     "tax_crime",
    "조세범처벌절차법": "tax_crime_proc",
}


def extract_meta(data: dict) -> dict | None:
    """JSON에서 기본정보 추출"""
    if not data:
        return None
    first_key = next(iter(data), None)
    if not first_key:
        return None
    root = data[first_key]
    info = root.get("기본정보", {})
    if not info:
        return None

    law_name = (info.get("법령명_한글") or info.get("법령명") or first_key)
    if isinstance(law_name, str):
        law_name = law_name.strip()

    law_type = info.get("법종구분", "")
    if isinstance(law_type, dict):
        law_type = law_type.get("content", "")
    law_type = str(law_type).strip()

    mst = info.get("법령MST") or info.get("법령키") or info.get("법령ID") or ""

    pno = str(info.get("공포번호", "")).strip()
    pdate = str(info.get("공포일자", "")).strip()
    eff_date = str(info.get("시행일자", "")).strip()

    if not (pdate and pno):
        return None

    return {
        "law_name": law_name,
        "pdate":    pdate,
        "pno":      pno,
        "eff_date": eff_date,
        "law_type": law_type,
        "mst":      str(mst),
    }


def classify_law_name(law_name: str) -> str:
    if "시행규칙" in law_name:
        return "rule"
    if "시행령" in law_name:
        return "decree"
    return "law"


def build_index_for_slug(slug: str) -> None:
    out_dir = LAW_DIR / slug
    if not out_dir.exists():
        print(f"  [SKIP] 폴더 없음: {out_dir}")
        return

    for subdir in ("law", "decree", "rule"):
        sub_path = out_dir / subdir
        if not sub_path.exists():
            continue

        files = list(sub_path.glob("MST_*.json"))
        if not files:
            continue

        index: dict[str, dict] = {}
        skipped = 0

        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                meta = extract_meta(data)
                if meta and meta["pdate"] and meta["pno"]:
                    pno_key = meta["pno"].lstrip("0")
                    index[pno_key] = {
                        "version_key": f"{meta['pdate']}_{meta['pno']}",
                        "pdate":    meta["pdate"],
                        "pno":      meta["pno"],
                        "eff_date": meta.get("eff_date", ""),
                        "law_name": meta.get("law_name", ""),
                        "mst":      meta.get("mst", ""),
                        "file":     f.name,
                    }
                else:
                    skipped += 1
            except Exception as e:
                print(f"    [ERR] {f.name}: {e}")
                skipped += 1

        idx_file = sub_path / "_version_index.json"
        idx_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

        # 날짜 범위 확인
        if index:
            dates = sorted(v["pdate"] for v in index.values())
            print(f"  [{subdir}] {len(index)}개 버전 ({dates[0]} ~ {dates[-1]}) → {idx_file.name}")
        else:
            print(f"  [{subdir}] 0개 (skipped={skipped})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--law", type=str, default=None)
    args = parser.parse_args()

    targets = SLUGS
    if args.law:
        targets = {k: v for k, v in SLUGS.items() if args.law in k}
        if not targets:
            print(f"[ERR] '{args.law}' 없음")
            return

    for law_name, slug in targets.items():
        print(f"\n[{law_name}] 인덱스 빌드...")
        build_index_for_slug(slug)

    print("\n완료!")


if __name__ == "__main__":
    main()
