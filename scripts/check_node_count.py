import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import dotenv; dotenv.load_dotenv()
from neo4j import GraphDatabase

URI  = os.getenv('NEO4J_URI')
AUTH = (os.getenv('NEO4J_USERNAME', 'neo4j'), os.getenv('NEO4J_PASSWORD'))
d = GraphDatabase.driver(URI, auth=AUTH)
with d.session() as s:
    total = s.run('MATCH (n) RETURN count(n) AS n').single()['n']
    print(f'전체 노드: {total:,} / 200,000 한계 ({total*100//200000}% 사용)')
    print(f'남은 여유: {200000 - total:,}개')
    labels = s.run("""
        MATCH (n)
        UNWIND labels(n) AS lbl
        RETURN lbl, count(*) AS cnt
        ORDER BY cnt DESC
    """).data()
    print('\n레이블별:')
    for row in labels[:20]:
        print(f'  {row["lbl"]:25s}: {row["cnt"]:>7,}')
d.close()
