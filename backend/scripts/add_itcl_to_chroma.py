"""
Railway cold-start 보조 스크립트: law_articles 컬렉션에 ITCL 조문 추가.

start.py에서 호출. ITCL이 이미 있으면 스킵.
데이터: /app/data/itcl_articles.pkl (임베딩 포함, 353건)
"""
import os
import pickle
import sys
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data" / "itcl_articles.pkl"
CHROMA_DIR = Path(os.environ.get("CHROMA_DIR", "/app/chroma"))


def run():
    if not DATA_FILE.exists():
        print("[add_itcl] data file not found:", DATA_FILE, "- skip")
        return

    # chromadb 0.6.x stores sqlite at {CHROMA_DIR}/chroma/chroma.sqlite3
    # older versions at {CHROMA_DIR}/chroma.sqlite3
    sqlite_paths = [
        CHROMA_DIR / "chroma.sqlite3",
        CHROMA_DIR / "chroma" / "chroma.sqlite3",
    ]
    if not any(p.exists() for p in sqlite_paths):
        print("[add_itcl] Chroma DB not found:", CHROMA_DIR, "- skip")
        return

    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(CHROMA_DIR))

        try:
            col = client.get_collection(name="law_articles")
        except Exception:
            col = client.create_collection(
                name="law_articles",
                metadata={"hnsw:space": "cosine"},
            )

        existing = col.get(where={"slug": "itcl"}, limit=1)
        if existing["ids"]:
            print("[add_itcl] ITCL already exists:", existing["ids"][0], "- skip")
            return

        with open(DATA_FILE, "rb") as f:
            data = pickle.load(f)

        ids = data["ids"]
        embeddings = data["embeddings"]
        documents = data["documents"]
        metadatas = data["metadatas"]

        # 인코딩 깨진 메타데이터 건너뜀
        valid = [
            (i, e, d, m)
            for i, e, d, m in zip(ids, embeddings, documents, metadatas)
            if i and d
        ]
        if not valid:
            print("[add_itcl] 유효 항목 없음 — 스킵")
            return

        v_ids, v_embs, v_docs, v_metas = zip(*valid)

        BATCH = 100
        for start in range(0, len(v_ids), BATCH):
            end = start + BATCH
            col.upsert(
                ids=list(v_ids[start:end]),
                embeddings=list(v_embs[start:end]),
                documents=list(v_docs[start:end]),
                metadatas=list(v_metas[start:end]),
            )

        print(f"[add_itcl] ITCL {len(v_ids)}건 추가 완료")

    except Exception as e:
        print(f"[add_itcl] 오류 (비치명적): {e}")


if __name__ == "__main__":
    run()
