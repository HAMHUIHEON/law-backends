import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import dotenv; dotenv.load_dotenv()
from neo4j import GraphDatabase

URI = os.getenv('NEO4J_URI')
AUTH = (os.getenv('NEO4J_USERNAME', 'neo4j'), os.getenv('NEO4J_PASSWORD'))
d = GraphDatabase.driver(URI, auth=AUTH)

with d.session() as s:
    # How many NULL LawTargets have a matching LawVersion?
    r = s.run("""
        MATCH (lt:LawTarget)
        WHERE lt.resolved_version_key IS NULL
        WITH count(lt) AS null_total
        CALL {
            MATCH (lt:LawTarget)
            WHERE lt.resolved_version_key IS NULL
            MATCH (v:LawVersion {scope: lt.scope, law_id: lt.law_id, version_key: lt.version_key})
            RETURN count(lt) AS matchable
        }
        RETURN null_total, matchable, null_total - matchable AS no_version
    """).single()
    print(f"NULL 전체:         {r['null_total']}")
    print(f"LawVersion 있음:   {r['matchable']}")
    print(f"LawVersion 없음:   {r['no_version']}")

d.close()
