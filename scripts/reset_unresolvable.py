"""UNRESOLVABLE LawTarget 리셋 — 재실행 전 처리."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
import dotenv
dotenv.load_dotenv()
from neo4j import GraphDatabase

URI  = os.getenv("NEO4J_URI")
AUTH = (os.getenv("NEO4J_USERNAME", "neo4j"), os.getenv("NEO4J_PASSWORD"))
driver = GraphDatabase.driver(URI, auth=AUTH)

with driver.session() as s:
    r = s.run("""
        MATCH (lt:LawTarget)
        WHERE lt.resolved_version_key = 'UNRESOLVABLE'
        REMOVE lt.resolved_version_key, lt.unresolvable_reason
        RETURN count(lt) AS reset_count
    """).single()
    print(f"Reset {r['reset_count']} UNRESOLVABLE LawTarget nodes")

driver.close()
