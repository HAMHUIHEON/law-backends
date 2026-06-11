# backend/db/neo4j_client.py
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

_driver = None

def get_driver():
    global _driver
    if _driver is None:
        if not NEO4J_URI:
            raise RuntimeError("NEO4J_URI is not configured")
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    return _driver

driver = None  # backward-compat alias — call get_driver() for actual use

if __name__ == "__main__":
    with driver.session() as session:
        result = session.run("RETURN 1 AS ok")
        print(result.single()["ok"])
