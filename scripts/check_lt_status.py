import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import dotenv; dotenv.load_dotenv()
from neo4j import GraphDatabase

URI = os.getenv('NEO4J_URI')
AUTH = (os.getenv('NEO4J_USERNAME', 'neo4j'), os.getenv('NEO4J_PASSWORD'))
d = GraphDatabase.driver(URI, auth=AUTH)

with d.session() as s:
    r = s.run("""
        MATCH (lt:LawTarget)
        RETURN
          count(lt) AS total,
          sum(CASE WHEN lt.resolved_version_key IS NOT NULL AND lt.resolved_version_key <> 'UNRESOLVABLE' THEN 1 ELSE 0 END) AS resolved,
          sum(CASE WHEN lt.resolved_version_key = 'UNRESOLVABLE' THEN 1 ELSE 0 END) AS unresolvable,
          sum(CASE WHEN lt.resolved_version_key IS NULL THEN 1 ELSE 0 END) AS pending
    """).single()
    total = r['total']
    resolved = r['resolved']
    print(f"전체:         {total}")
    print(f"해소됨:       {resolved}  ({resolved*100//total if total else 0}%)")
    print(f"UNRESOLVABLE: {r['unresolvable']}")
    print(f"미처리(NULL): {r['pending']}")

    reasons = s.run("""
        MATCH (lt:LawTarget) WHERE lt.resolved_version_key = 'UNRESOLVABLE'
        RETURN lt.unresolvable_reason AS r, count(*) AS n ORDER BY n DESC
    """).data()
    print("UNRESOLVABLE 사유:")
    for row in reasons:
        print(f"  {str(row['r']):20s}: {row['n']}")

d.close()
