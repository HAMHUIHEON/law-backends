"""
SemanticIssue 노드에 벡터 임베딩을 추가하고 ITCL 벡터 인덱스를 생성한다.

- 임베딩 대상: SemanticIssue.title + SemanticIssue.summary
- 모델: text-embedding-3-small (1536dim)
- 배치 처리: 100개씩 (OpenAI 속도 제한 대응)
- 인덱스: itcl_issue_embedding (SemanticIssue.embedding)

이미 embedding이 있는 노드는 건너뜀 (idempotent).
"""

import os, sys, time, json
from pathlib import Path
import dotenv

dotenv.load_dotenv()

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from neo4j import GraphDatabase
import openai

EMBED_MODEL = "text-embedding-3-small"
BATCH_SIZE = 100

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
)
oai = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def create_vector_index():
    cypher = """
    CREATE VECTOR INDEX itcl_issue_embedding IF NOT EXISTS
    FOR (si:SemanticIssue) ON si.embedding
    OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}
    """
    with driver.session() as s:
        s.run(cypher)
    print("✅ 벡터 인덱스 생성/확인: itcl_issue_embedding")


def fetch_unembedded_issues():
    cypher = """
    MATCH (si:SemanticIssue)
    WHERE si.embedding IS NULL
    RETURN si.scope AS scope, si.set_key AS set_key, si.id AS id,
           si.issue_id AS issue_id, si.title AS title, si.summary AS summary
    ORDER BY si.id
    """
    with driver.session() as s:
        return s.run(cypher).data()


def embed_texts(texts: list[str]) -> list[list[float]]:
    resp = oai.embeddings.create(model=EMBED_MODEL, input=texts)
    return [r.embedding for r in resp.data]


def write_embeddings(rows: list[dict], embeddings: list[list[float]]):
    batch = [
        {"id": r["id"], "embedding": emb}
        for r, emb in zip(rows, embeddings)
    ]
    cypher = """
    UNWIND $batch AS item
    MATCH (si:SemanticIssue {id: item.id})
    SET si.embedding = item.embedding
    """
    with driver.session() as s:
        s.run(cypher, batch=batch)


def build_embed_text(row: dict) -> str:
    title = (row.get("title") or row.get("issue_id") or "").strip()
    summary = (row.get("summary") or "").strip()
    if summary:
        return f"{title}: {summary}"
    return title


def main():
    create_vector_index()

    issues = fetch_unembedded_issues()
    total = len(issues)
    print(f"\n임베딩 대상: {total}개 (embedding=NULL)")

    if total == 0:
        print("✅ 모두 임베딩 완료 (스킵)")
        return

    done = 0
    for i in range(0, total, BATCH_SIZE):
        batch = issues[i : i + BATCH_SIZE]
        texts = [build_embed_text(r) for r in batch]
        embeddings = embed_texts(texts)
        write_embeddings(batch, embeddings)
        done += len(batch)
        print(f"  [{done}/{total}] 완료")
        if done < total:
            time.sleep(0.3)  # 속도 제한 여유

    print(f"\n✅ SemanticIssue 임베딩 완료: {done}개")


if __name__ == "__main__":
    main()
    driver.close()
