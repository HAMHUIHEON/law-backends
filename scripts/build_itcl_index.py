"""ITCL _version_index.json 빌드 — law/itcl/{law,decree,rule}/*.json 처리."""
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

ROOT    = Path(__file__).parent.parent
ITCL_DIR = ROOT / "law" / "itcl"

for kind in ("law", "decree", "rule"):
    sub = ITCL_DIR / kind
    if not sub.exists():
        print(f"  [SKIP] {kind} 폴더 없음")
        continue

    files = [f for f in sub.glob("*.json") if f.name != "_version_index.json"]
    if not files:
        print(f"  [SKIP] {kind} JSON 없음")
        continue

    index: dict[str, dict] = {}
    skipped = 0
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            root = data.get("법령", {})
            info = root.get("기본정보", {})
            if not info:
                skipped += 1
                continue
            pno   = str(info.get("공포번호", "")).strip()
            pdate = str(info.get("공포일자", "")).strip()
            if not (pno and pdate):
                skipped += 1
                continue
            eff_date  = str(info.get("시행일자", "")).strip()
            law_name  = str(info.get("법령명_한글") or info.get("법령명") or "").strip()
            mst       = str(info.get("법령MST") or info.get("법령키") or info.get("법령ID") or "").strip()
            pno_key   = pno.lstrip("0")
            index[pno_key] = {
                "version_key": f"{pdate}_{pno}",
                "pdate":    pdate,
                "pno":      pno,
                "eff_date": eff_date,
                "law_name": law_name,
                "mst":      mst,
                "file":     f.name,
            }
        except Exception as e:
            print(f"    [ERR] {f.name}: {e}")
            skipped += 1

    idx_path = sub / "_version_index.json"
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    if index:
        dates = sorted(v["pdate"] for v in index.values())
        print(f"  [{kind}] {len(index)}개 버전 ({dates[0]} ~ {dates[-1]}) → _version_index.json (skip={skipped})")
    else:
        print(f"  [{kind}] 0개 (skip={skipped})")

print("\n완료!")
