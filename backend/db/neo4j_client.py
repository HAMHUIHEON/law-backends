# backend/db/neo4j_client.py
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.environ["NEO4J_URI"]              # neo4j+s://xxxx.databases.neo4j.io
NEO4J_USERNAME = os.environ["NEO4J_USERNAME"]    # 보통 "neo4j"
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
)

if __name__ == "__main__":
    with driver.session() as session:
        result = session.run("RETURN 1 AS ok")
        print(result.single()["ok"])
