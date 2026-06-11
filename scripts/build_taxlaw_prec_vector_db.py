"""
taxlaw.nts.go.kr 판례(prec) 벡터 DB 구축 — Chroma + text-embedding-3-small

소스: taxlaw/data/prec/prec.jsonl  (62,000+건)
임베딩 텍스트: [세법] [결정유형] 쟁점명 + 요지
컬렉션: taxlaw_prec
저장 위치: vector_db/chroma

실행:
  python scripts/build_taxlaw_prec_vector_db.py           # 신규/증분 구축
  python scripts/build_taxlaw_prec_vector_db.py --reset   # 초기화 후 재구축
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import dotenv
dotenv.load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

import chromadb
from chromadb.utils import embedding_functions

ROOT       = Path(__file__).parent.parent
JSONL_PATH = ROOT / "taxlaw" / "data" / "prec" / "prec.jsonl"
CHROMA_DIR = ROOT / "vector_db" / "chroma"

OPENAI_KEY  = os.getenv("OPENAI_API_KEY", "")
COLLECTION  = "taxlaw_prec"
BATCH_SIZE  = 100
MIN_TEXT_LEN = 10


def _build_doc_text(r: dict) -> str:
    parts = []
    tlaw = r.get("NTST_TLAW_CL_NM", "").strip()
    dcs  = r.get("NTST_DCM_DCS_CL_NM", "").strip()   # 국승/국패/일부국패 등
    ttl  = r.get("TTL", "").strip()
    gist = r.get("GIST_CNTN", "").strip()

    if tlaw:
        parts.append(f"[세법: {tlaw}]")
    if dcs:
        parts.append(f"[결정: {dcs}]")
    if ttl:
        parts.append(ttl)
    if gist:
        parts.append(gist[:500])
    return "\n".join(parts)


def _build_metadata(r: dict) -> dict:
    return {
        "doc_id":        str(r.get("DOC_ID", "")),
        "case_no":       r.get("NTST_DCM_DSCM_CNTN", "")[:100],  # 대법원-2025-두-34754
        "attr_yr":       str(r.get("ATTR_YR", "")),
        "tax_type":      r.get("NTST_TLAW_CL_NM", "")[:50],
        "decision":      r.get("NTST_DCM_DCS_CL_NM", "")[:30],   # 국승/국패 등
        "title":         r.get("TTL", "")[:200],
        "has_full_text": "Y" if r.get("FILE_CN", "").strip() else "N",
    }


def get_collection(reset: bool = False) -> chromadb.Collection:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_KEY,
        model_name="text-embedding-3-small",
    )

    if reset:
        try:
            client.delete_collection(COLLECTION)
            print("기존 컬렉션 삭제 완료")
        except Exception:
            pass

    return client.get_or_create_collection(
        name=COLLECTION,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def get_existing_ids(col: chromadb.Collection) -> set[str]:
    try:
        return set(col.get(include=[])["ids"])
    except Exception:
        return set()


def run(reset: bool = False) -> None:
    if not JSONL_PATH.exists():
        print(f"소스 없음: {JSONL_PATH}")
        return

    col = get_collection(reset=reset)
    existing_ids = get_existing_ids(col)
    print(f"기존 인제스트: {len(existing_ids)}건")

    docs, metas, ids = [], [], []
    skipped_dup = 0
    skipped_short = 0
    total_read = 0
    saved = 0
    t0 = time.time()

    def _flush(force: bool = False) -> None:
        nonlocal docs, metas, ids, saved
        if not docs:
            return
        if not force and len(docs) < BATCH_SIZE:
            return
        col.upsert(documents=docs, metadatas=metas, ids=ids)
        saved += len(docs)
        docs, metas, ids = [], [], []

    with JSONL_PATH.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue

            total_read += 1
            doc_id = f"taxlaw_prec__{r.get('DOC_ID', total_read)}"

            if doc_id in existing_ids:
                skipped_dup += 1
                continue

            text = _build_doc_text(r)
            if len(text) < MIN_TEXT_LEN:
                skipped_short += 1
                continue

            docs.append(text)
            metas.append(_build_metadata(r))
            ids.append(doc_id)

            if len(docs) >= BATCH_SIZE:
                _flush(force=True)

            if total_read % 5000 == 0:
                elapsed = time.time() - t0
                pct = (saved + skipped_dup) / max(total_read, 1) * 100
                print(
                    f"[{total_read:,}건 읽음] 인제스트 {saved:,} | "
                    f"중복 {skipped_dup} | {elapsed:.0f}s | {pct:.0f}%",
                    flush=True,
                )

    _flush(force=True)

    elapsed = time.time() - t0
    final_count = col.count()
    print(f"\n완료 — 컬렉션 총 {final_count:,}건 / {elapsed:.0f}s")
    print(f"  신규 인제스트: {saved}건, 중복 스킵: {skipped_dup}건, 텍스트 부족: {skipped_short}건")
    print(f"  저장 위치: {CHROMA_DIR}")


def main() -> None:
    ap = argparse.ArgumentParser(description="taxlaw prec 벡터 DB 구축")
    ap.add_argument("--reset", action="store_true", help="컬렉션 초기화 후 재구축")
    args = ap.parse_args()
    run(reset=args.reset)


if __name__ == "__main__":
    main()
