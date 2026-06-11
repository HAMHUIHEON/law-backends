"""
ITCL_integrated 캐시 → Neo4j ingest (전체 20개 set_key)

Norm 레이어(Law/Chapter/Article)가 없으므로 link_all_integrated_chapters는
OPTIONAL MATCH 덕에 에러 없이 스킵됨 (DERIVED_FROM 관계만 생성 안 됨).

set_key에서 snapshot 메타를 자동 파싱:
  LAW_20251223_21215__DECREE_... → valid_from = "20251223"
"""
import os, json, sys, re
from pathlib import Path
from neo4j import GraphDatabase
import dotenv
dotenv.load_dotenv()

# ── 경로 설정 ──────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

CACHE_ROOT = ROOT / "cache" / "ITCL_integrated"

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
)

# ── set_key 목록 (시간순 정렬) ──────────────────────────────────────
SET_KEY_RE = re.compile(
    r"^LAW_(?P<law_date>\d{8})_\d+__DECREE_(?P<dec_date>\d{8})_\d+__RULE_(?P<rule_date>\d{8})_\d+$"
)

def parse_law_date(set_key: str) -> str:
    m = SET_KEY_RE.match(set_key)
    return m.group("law_date") if m else "00000000"

set_keys = sorted(
    [d.name for d in CACHE_ROOT.iterdir() if d.is_dir() and SET_KEY_RE.match(d.name)],
    key=parse_law_date,
)
print(f"발견된 set_key: {len(set_keys)}개\n")

# valid_from/valid_to 계산 (연속 구간)
def build_snapshots(keys):
    result = []
    for i, k in enumerate(keys):
        m = SET_KEY_RE.match(k)
        law_date = m.group("law_date")
        valid_to = parse_law_date(keys[i + 1]) if i + 1 < len(keys) else None
        result.append({
            "set_key": k,
            "valid_from": law_date,
            "valid_to": valid_to,
            "law": {
                "promulgated_at": law_date,
                "effective_at": law_date,
            },
        })
    return result

snapshots = build_snapshots(set_keys)

# ── ingest ─────────────────────────────────────────────────────────
from ITCL_integrated.ingest import IntegratedIngestContext, run_full_integrated_ingest

ok, fail = 0, 0
for snap in snapshots:
    sk = snap["set_key"]
    p  = CACHE_ROOT / sk

    sem_path  = p / "02_semantic_dict.json"
    rea_path  = p / "03_reasoning_dict.json"
    enr_path  = p / "05_reasoning_enriched.json"

    if not all(f.exists() for f in [sem_path, rea_path, enr_path]):
        print(f"  ⚠️  캐시 불완전 — 건너뜀: {sk}")
        fail += 1
        continue

    print(f"  → {sk}  (valid_from={snap['valid_from']}, valid_to={snap['valid_to']})")

    with open(sem_path, encoding="utf-8") as f:
        semantic = json.load(f)
    with open(rea_path, encoding="utf-8") as f:
        reasoning = json.load(f)

    ctx = IntegratedIngestContext(
        semantic_dict=semantic,
        reasoning_dict=reasoning,
        reasoning_enriched_path=str(enr_path),
        set_key=sk,
    )

    try:
        run_full_integrated_ingest(driver, ctx, snapshot=snap)
        print(f"     ✅ 완료")
        ok += 1
    except Exception as e:
        print(f"     ❌ 실패: {e}")
        fail += 1

driver.close()
print(f"\n=== 결과: 성공 {ok}개 / 실패 {fail}개 ===")
