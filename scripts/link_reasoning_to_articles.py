"""
Phase 1 마무리: Norm 레이어 복원 완료 후 실행

단계:
  1) IntegratedChapter → Chapter DERIVED_FROM 링크
  2) ReasoningStep → Article / IntegratedLawTarget BASED_ON 링크
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

CACHE_ROOT = ROOT / "cache" / "ITCL_integrated"
SET_KEY_RE = re.compile(
    r"^LAW_\d{8}_\w+__DECREE_\d{8}_\w+__RULE_\d{8}_\w+$"
)
set_keys = sorted(d.name for d in CACHE_ROOT.iterdir() if d.is_dir() and SET_KEY_RE.match(d.name))
print(f"set_key 수: {len(set_keys)}개\n")

# ──────────────────────────────────────────────────────────────────────
# 1. IntegratedChapter → Chapter DERIVED_FROM 링크
# ──────────────────────────────────────────────────────────────────────

from ITCL_integrated.ingest import link_all_integrated_chapters

print("=== 1. IntegratedChapter → Chapter DERIVED_FROM 링크 ===")
ok_link = fail_link = 0
for sk in set_keys:
    sem_path = CACHE_ROOT / sk / "02_semantic_dict.json"
    if not sem_path.exists():
        print(f"  ⚠️  semantic_dict 없음: {sk[-50:]}")
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

with driver.session() as s:
    total_ic = s.run("MATCH (ic:IntegratedChapter) RETURN count(ic) AS n").single()["n"]
    linked_ic = s.run(
        "MATCH (ic:IntegratedChapter)-[:DERIVED_FROM]->() RETURN count(ic) AS n"
    ).single()["n"]
    print(f"  → IntegratedChapter {total_ic}개 중 {linked_ic}개 Chapter 연결됨\n")

# ──────────────────────────────────────────────────────────────────────
# 2. ReasoningStep → Article BASED_ON 링크
# ──────────────────────────────────────────────────────────────────────

from ITCL_integrated.connect_rs_to_article import ingest_reasoning_steps

print("=== 2. ReasoningStep → Article/LawTarget BASED_ON 링크 ===")
ok_rs = fail_rs = 0
for sk in set_keys:
    enr_path = CACHE_ROOT / sk / "05_reasoning_enriched.json"
    if not enr_path.exists():
        print(f"  ⚠️  05_reasoning_enriched.json 없음: {sk[-50:]}")
        fail_rs += 1
        continue
    with open(enr_path, encoding="utf-8") as f:
        reasoning_json = json.load(f)
    try:
        ingest_reasoning_steps(driver, reasoning_json=reasoning_json, set_key=sk)
        ok_rs += 1
        print(f"  ✅ {sk[-60:]}")
    except Exception as e:
        print(f"  ❌ {sk[-60:]}: {e}")
        fail_rs += 1

print(f"\n  완료: 성공 {ok_rs} / 실패 {fail_rs}")

# ──────────────────────────────────────────────────────────────────────
# 3. 최종 현황
# ──────────────────────────────────────────────────────────────────────

print("\n=== 최종 Neo4j 현황 ===")
labels = [
    ("IntegratedSnapshot", "IntegratedSnapshot"),
    ("IntegratedChapter", "IntegratedChapter"),
    ("SemanticIssue", "SemanticIssue"),
    ("ReasoningIssue", "ReasoningIssue"),
    ("ReasoningStep", "ReasoningStep"),
    ("Law", "Law"),
    ("LawVersion", "LawVersion"),
    ("Chapter", "Chapter"),
    ("Article", "Article"),
]
rels = [
    "DERIVED_FROM", "HAS_VERSION", "HAS_CHAPTER", "HAS_ARTICLE",
    "BASED_ON", "HAS_INTEGRATED_SEMANTIC", "HAS_INTEGRATED_REASONING",
]

with driver.session() as s:
    for label, _ in labels:
        n = s.run(f"MATCH (n:{label}) RETURN count(n) AS n").single()["n"]
        print(f"  {label:30s}: {n:>6}")
    print()
    for rel in rels:
        r = s.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS n").single()["n"]
        print(f"  {rel:35s}: {r:>6}")

driver.close()
print("\n✅ Phase 1 완료")
