"""
Norm 레이어 복원: Law / LawVersion / Chapter / Section / Article 노드 생성

단계:
  1) Norm 레이어 제약 조건 설정
  2) 20개 set_key에서 사용된 고유 DRF 파일 목록 추출
  3) convert_drf_law_to_unified → run_ingest_norm (LLM 없음, 구조만)
  4) IntegratedChapter → Chapter DERIVED_FROM 링크 (re-link)

LLM(NormUnit/CrossRef) 없이 Law/LawVersion/Chapter/Article 뼈대만 복원한다.
"""

import os, json, sys, re
from pathlib import Path

import dotenv
dotenv.load_dotenv()

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
)

# ──────────────────────────────────────────────────────────────────────
# 1. Norm 레이어 제약 조건
# ──────────────────────────────────────────────────────────────────────

NORM_CONSTRAINTS = [
    "CREATE CONSTRAINT law_key IF NOT EXISTS FOR (l:Law) REQUIRE (l.scope, l.id) IS UNIQUE",
    "CREATE CONSTRAINT law_version_key IF NOT EXISTS FOR (v:LawVersion) REQUIRE (v.scope, v.law_id, v.version_key) IS UNIQUE",
    "CREATE CONSTRAINT chapter_key IF NOT EXISTS FOR (c:Chapter) REQUIRE (c.scope, c.version_key, c.id) IS UNIQUE",
    "CREATE CONSTRAINT section_key IF NOT EXISTS FOR (s:Section) REQUIRE (s.scope, s.version_key, s.id) IS UNIQUE",
    "CREATE CONSTRAINT subdivision_key IF NOT EXISTS FOR (sd:Subdivision) REQUIRE (sd.scope, sd.version_key, sd.id) IS UNIQUE",
    "CREATE CONSTRAINT article_key IF NOT EXISTS FOR (a:Article) REQUIRE (a.scope, a.version_key, a.id) IS UNIQUE",
    "CREATE CONSTRAINT paragraph_key IF NOT EXISTS FOR (p:Paragraph) REQUIRE (p.scope, p.version_key, p.id) IS UNIQUE",
    "CREATE CONSTRAINT item_key IF NOT EXISTS FOR (i:Item) REQUIRE (i.scope, i.version_key, i.id) IS UNIQUE",
    "CREATE CONSTRAINT subitem_key IF NOT EXISTS FOR (si:SubItem) REQUIRE (si.scope, si.version_key, si.id) IS UNIQUE",
    "CREATE CONSTRAINT addenda_key IF NOT EXISTS FOR (ad:Addenda) REQUIRE (ad.scope, ad.version_key, ad.id) IS UNIQUE",
    "CREATE CONSTRAINT normunit_key IF NOT EXISTS FOR (n:NormUnit) REQUIRE (n.scope, n.version_key, n.id) IS UNIQUE",
    "CREATE CONSTRAINT crossref_key IF NOT EXISTS FOR (r:CrossRef) REQUIRE (r.scope, r.version_key, r.from_id, r.target, r.type) IS UNIQUE",
    "CREATE CONSTRAINT lawtarget_key IF NOT EXISTS FOR (t:LawTarget) REQUIRE (t.scope, t.version_key, t.name) IS UNIQUE",
    "CREATE INDEX lawversion_current_lookup IF NOT EXISTS FOR (v:LawVersion) ON (v.scope, v.law_id, v.is_current)",
    "CREATE INDEX chapter_by_version IF NOT EXISTS FOR (c:Chapter) ON (c.scope, c.version_key, c.id)",
]

print("=== 1. Norm 레이어 제약 조건 설정 ===")
with driver.session() as s:
    for stmt in NORM_CONSTRAINTS:
        try:
            s.run(stmt)
            print(f"  ✅ {stmt[:70]}")
        except Exception as e:
            print(f"  ⚠️  {stmt[:50]} → {e}")

# ──────────────────────────────────────────────────────────────────────
# 2. 20개 set_key에서 고유 DRF 목록 추출
# ──────────────────────────────────────────────────────────────────────

CACHE_ROOT = ROOT / "cache" / "ITCL_integrated"
SET_KEY_RE = re.compile(
    r"^LAW_(?P<law_d>\d{8})_(?P<law_n>\w+)__"
    r"DECREE_(?P<dec_d>\d{8})_(?P<dec_n>\w+)__"
    r"RULE_(?P<rule_d>\d{8})_(?P<rule_n>\w+)$"
)

set_keys = [d.name for d in CACHE_ROOT.iterdir() if d.is_dir() and SET_KEY_RE.match(d.name)]

unique_drfs: dict[str, str] = {}  # "TYPE:YYYYMMDD_NUM" → drf_key

for sk in set_keys:
    m = SET_KEY_RE.match(sk)
    unique_drfs[f"LAW:{m['law_d']}_{m['law_n']}"] = sk
    unique_drfs[f"DECREE:{m['dec_d']}_{m['dec_n']}"] = sk
    unique_drfs[f"RULE:{m['rule_d']}_{m['rule_n']}"] = sk

print(f"\n=== 2. 고유 DRF: {len(unique_drfs)}개 ===")
for k in sorted(unique_drfs):
    print(f"  {k}")

# DRF 경로 인덱스 로드
INDEX_PATH = ROOT / "cache" / "drf_path_index_itcl.json"
with open(INDEX_PATH, encoding="utf-8") as f:
    drf_index = json.load(f)

# ──────────────────────────────────────────────────────────────────────
# 3. convert + ingest_norm (LLM 없음)
# ──────────────────────────────────────────────────────────────────────

from ITCL.convert_drf_law_to_unified import convert_drf_law_to_unified
import ITCL.ingest_norm_itcl as _norm_mod

# ingest_norm_itcl uses its own module-level driver — override with ours
_norm_mod.driver = driver

from ITCL.ingest_norm_itcl import run_ingest_norm

print("\n=== 3. Norm 레이어 ingest 시작 ===")
ok = fail = skip = 0

for drf_key in sorted(unique_drfs):
    if drf_key not in drf_index:
        print(f"  ❌ DRF 경로 없음: {drf_key}")
        fail += 1
        continue

    fpath = drf_index[drf_key]
    try:
        with open(fpath, encoding="utf-8") as f:
            raw_drf = json.load(f)

        unified = convert_drf_law_to_unified(raw_drf)
        run_ingest_norm(unified)
        print(f"  ✅ {drf_key}")
        ok += 1
    except Exception as e:
        print(f"  ❌ {drf_key}: {e}")
        fail += 1

print(f"\n  완료: 성공 {ok} / 실패 {fail} / 총 {len(unique_drfs)}개")

# ──────────────────────────────────────────────────────────────────────
# 4. IntegratedChapter → Chapter DERIVED_FROM 링크 복원
# ──────────────────────────────────────────────────────────────────────

from ITCL_integrated.ingest import link_all_integrated_chapters

print("\n=== 4. IntegratedChapter → Chapter DERIVED_FROM 링크 복원 ===")

ok_link = fail_link = 0
for sk in sorted(set_keys):
    sem_path = CACHE_ROOT / sk / "02_semantic_dict.json"
    if not sem_path.exists():
        print(f"  ⚠️  semantic_dict 없음: {sk}")
        fail_link += 1
        continue
    with open(sem_path, encoding="utf-8") as f:
        semantic_dict = json.load(f)
    try:
        with driver.session() as s:
            link_all_integrated_chapters(s, set_key=sk, semantic_dict=semantic_dict)
        ok_link += 1
        print(f"  ✅ {sk[-60:]}")
    except Exception as e:
        print(f"  ❌ {sk[-60:]}: {e}")
        fail_link += 1

print(f"\n  링크 완료: 성공 {ok_link} / 실패 {fail_link}")

# 실제 링크된 IntegratedChapter 수 확인
with driver.session() as s:
    total_ic = s.run("MATCH (ic:IntegratedChapter) RETURN count(ic) AS n").single()["n"]
    linked_ic = s.run(
        "MATCH (ic:IntegratedChapter)-[:DERIVED_FROM]->() RETURN count(ic) AS n"
    ).single()["n"]
    print(f"  IntegratedChapter 전체 {total_ic}개 중 {linked_ic}개 Chapter 연결됨")

driver.close()
print("\n✅ Norm 레이어 복원 완료")
