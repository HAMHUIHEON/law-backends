import os, dotenv, time
dotenv.load_dotenv()
from neo4j import GraphDatabase

uri  = os.getenv('NEO4J_URI')
auth = (os.getenv('NEO4J_USERNAME','neo4j'), os.getenv('NEO4J_PASSWORD'))
print("URI:", uri)
t = time.time()
driver = GraphDatabase.driver(uri, auth=auth)
with driver.session() as s:
    cnt = s.run('MATCH (n) RETURN count(n) AS cnt').single()[0]
    print(f"Total nodes: {cnt}  ({time.time()-t:.1f}s)")
    laws = s.run('MATCH (l:Law) RETURN l.name AS name, l.scope AS scope ORDER BY l.scope, l.name').data()
    print(f"Laws: {len(laws)}")
    for r in laws:
        print(f"  [{r['scope']}] {r['name']}")
driver.close()
