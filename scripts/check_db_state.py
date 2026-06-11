import os, sys
from pathlib import Path
import dotenv
dotenv.load_dotenv()
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from neo4j import GraphDatabase
driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
)

labels = [
    "IntegratedSnapshot", "IntegratedChapter", "SemanticIssue", "ReasoningIssue", "ReasoningStep",
    "Law", "LawVersion", "Chapter", "Section", "Article"
]

print("=== Neo4j 노드 현황 ===")
with driver.session() as s:
    for label in labels:
        row = s.run(f"MATCH (n:{label}) RETURN count(n) AS n").single()
        print(f"  {label:30s}: {row['n']:>6}")

print("\n=== 관계 현황 ===")
rels = ["HAS_INTEGRATED_CHAPTER", "HAS_INTEGRATED_SEMANTIC", "HAS_INTEGRATED_REASONING",
        "DERIVED_FROM", "HAS_VERSION", "HAS_CHAPTER", "HAS_ARTICLE"]
with driver.session() as s:
    for rel in rels:
        row = s.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS n").single()
        print(f"  {rel:35s}: {row['n']:>6}")

driver.close()
