"""Neo4j IntegratedSnapshot 구조 확인"""
import os, sys, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
)

with driver.session() as s:
    # 1. IntegratedSnapshot 노드 존재 확인
    r = s.run("MATCH (n:IntegratedSnapshot) RETURN count(n) AS cnt").single()
    print("IntegratedSnapshot count:", r["cnt"] if r else 0)

    # 2. 샘플 set_key 몇 개
    rows = s.run(
        "MATCH (n:IntegratedSnapshot) "
        "RETURN n.set_key AS sk, n.valid_from AS vf, n.valid_to AS vt "
        "LIMIT 5"
    )
    print("\n--- Sample set_keys ---")
    for row in rows:
        print(json.dumps(dict(row), ensure_ascii=False))

    # 3. 공포번호 15221 검색 (법률 제15221호)
    print("\n--- Search for 15221 ---")
    rows2 = s.run(
        "MATCH (n:IntegratedSnapshot) "
        "WHERE n.set_key CONTAINS '15221' "
        "RETURN n.set_key AS sk, n.valid_from AS vf, n.valid_to AS vt "
        "LIMIT 5"
    )
    found = list(rows2)
    if found:
        for row in found:
            print(json.dumps(dict(row), ensure_ascii=False))
    else:
        print("NOT FOUND - trying broader search...")
        # 3b. 다른 노드 레이블에 set_key가 있는지 확인
        rows3 = s.run(
            "CALL db.labels() YIELD label RETURN label"
        )
        labels = [r["label"] for r in rows3]
        print("All labels:", labels)

        # 3c. set_key 속성 가진 노드 찾기
        rows4 = s.run(
            "MATCH (n) WHERE n.set_key IS NOT NULL "
            "RETURN labels(n) AS lbls, n.set_key AS sk "
            "LIMIT 5"
        )
        for row in rows4:
            print(json.dumps(dict(row), ensure_ascii=False))

driver.close()
