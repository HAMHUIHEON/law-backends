"""
Neo4j constraints 설정 — ingest 전 1회 실행 (또는 LAW_7/run_law7.py --reset 사용)

LAW_7 신규 스키마: Chapter/Article 등 중간 노드에 law_id 포함.
"""
import os
from neo4j import GraphDatabase
import dotenv
dotenv.load_dotenv()

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.getenv("NEO4J_USERNAME", "neo4j"), os.environ["NEO4J_PASSWORD"]),
)

CONSTRAINTS = [
    # ── 기존 제약 제거 ─────────────────────────────────────────────────────────
    "DROP CONSTRAINT law_key           IF EXISTS",
    "DROP CONSTRAINT law_version_key   IF EXISTS",
    "DROP CONSTRAINT chapter_key       IF EXISTS",
    "DROP CONSTRAINT section_key       IF EXISTS",
    "DROP CONSTRAINT subdivision_key   IF EXISTS",
    "DROP CONSTRAINT article_key       IF EXISTS",
    "DROP CONSTRAINT paragraph_key     IF EXISTS",
    "DROP CONSTRAINT item_key          IF EXISTS",
    "DROP CONSTRAINT subitem_key       IF EXISTS",
    "DROP CONSTRAINT normunit_key      IF EXISTS",
    "DROP CONSTRAINT semantic_issue_key   IF EXISTS",
    "DROP CONSTRAINT reasoning_issue_key  IF EXISTS",
    "DROP CONSTRAINT reasoning_step_key   IF EXISTS",
    "DROP CONSTRAINT integrated_snapshot_key        IF EXISTS",
    "DROP CONSTRAINT integrated_chapter_key         IF EXISTS",
    "DROP CONSTRAINT integrated_semantic_issue_key  IF EXISTS",
    "DROP CONSTRAINT integrated_reasoning_issue_key IF EXISTS",

    # ── Norm 레이어 (law_id 포함) ────────────────────────────────────────────
    "CREATE CONSTRAINT law_key IF NOT EXISTS FOR (l:Law) REQUIRE (l.scope, l.id) IS UNIQUE",
    "CREATE CONSTRAINT law_version_key IF NOT EXISTS FOR (v:LawVersion) REQUIRE (v.scope, v.law_id, v.version_key) IS UNIQUE",
    "CREATE CONSTRAINT chapter_key     IF NOT EXISTS FOR (c:Chapter)    REQUIRE (c.scope, c.law_id, c.version_key, c.id) IS UNIQUE",
    "CREATE CONSTRAINT section_key     IF NOT EXISTS FOR (s:Section)    REQUIRE (s.scope, s.law_id, s.version_key, s.id) IS UNIQUE",
    "CREATE CONSTRAINT subdivision_key IF NOT EXISTS FOR (sd:Subdivision) REQUIRE (sd.scope, sd.law_id, sd.version_key, sd.id) IS UNIQUE",
    "CREATE CONSTRAINT article_key     IF NOT EXISTS FOR (a:Article)    REQUIRE (a.scope, a.law_id, a.version_key, a.id) IS UNIQUE",
    "CREATE CONSTRAINT paragraph_key   IF NOT EXISTS FOR (p:Paragraph)  REQUIRE (p.scope, p.law_id, p.version_key, p.id) IS UNIQUE",
    "CREATE CONSTRAINT item_key        IF NOT EXISTS FOR (i:Item)       REQUIRE (i.scope, i.law_id, i.version_key, i.id) IS UNIQUE",
    "CREATE CONSTRAINT subitem_key     IF NOT EXISTS FOR (si:SubItem)   REQUIRE (si.scope, si.law_id, si.version_key, si.id) IS UNIQUE",
    "CREATE CONSTRAINT normunit_key    IF NOT EXISTS FOR (n:NormUnit)   REQUIRE (n.scope, n.law_id, n.version_key, n.id) IS UNIQUE",
    "CREATE CONSTRAINT semantic_issue_key  IF NOT EXISTS FOR (s:SemanticIssue)  REQUIRE (s.scope, s.law_id, s.version_key, s.id) IS UNIQUE",
    "CREATE CONSTRAINT reasoning_issue_key IF NOT EXISTS FOR (r:ReasoningIssue) REQUIRE (r.scope, r.law_id, r.version_key, r.id) IS UNIQUE",
    "CREATE CONSTRAINT reasoning_step_key  IF NOT EXISTS FOR (st:ReasoningStep) REQUIRE (st.scope, st.law_id, st.version_key, st.id) IS UNIQUE",

    # ── Integrated 레이어 ────────────────────────────────────────────────────
    "CREATE CONSTRAINT integrated_snapshot_key        IF NOT EXISTS FOR (s:IntegratedSnapshot) REQUIRE (s.scope, s.set_key) IS UNIQUE",
    "CREATE CONSTRAINT integrated_chapter_key         IF NOT EXISTS FOR (ic:IntegratedChapter) REQUIRE (ic.scope, ic.set_key, ic.chapter_id) IS UNIQUE",
    "CREATE CONSTRAINT integrated_semantic_issue_key  IF NOT EXISTS FOR (s:SemanticIssue)  REQUIRE (s.scope, s.set_key, s.id) IS UNIQUE",
    "CREATE CONSTRAINT integrated_reasoning_issue_key IF NOT EXISTS FOR (r:ReasoningIssue) REQUIRE (r.scope, r.set_key, r.id) IS UNIQUE",

    # ── 인덱스 ──────────────────────────────────────────────────────────────
    "CREATE INDEX lawversion_current IF NOT EXISTS FOR (v:LawVersion) ON (v.scope, v.law_id, v.is_current)",
]

print("=== constraints 설정 시작 ===")
with driver.session() as s:
    for cypher in CONSTRAINTS:
        stmt = cypher.strip()
        if not stmt:
            continue
        try:
            s.run(stmt)
            label = stmt.split("\n")[0][:60]
            print(f"  ✅ {label}")
        except Exception as e:
            print(f"  ⚠️  {stmt[:60]} → {e}")

print()
print("=== 현재 constraints 목록 ===")
with driver.session() as s:
    rows = s.run("SHOW CONSTRAINTS")
    for r in rows:
        print(f"  {r['name']:45s}  {r['type']}")

driver.close()
print("\n완료.")
