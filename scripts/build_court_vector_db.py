"""
court_cases Chroma 컬렉션 빌드

소스:
  1. cases/court/*.json (PDF 추출 메타)
     + cache/{case_id}/narrative.json   (fact_summary, core_conflicts, arguments)
     + cache/{case_id}/issue_logic.json (issue_logic_chains)
     + cache/{case_id}/metadata.json    (사건번호, 법원, 선고일 등)
  2. cases/court_api/*.json — DRF API 수집본 (파이프라인 미적용, 원문 텍스트)

이미 임베딩된 doc_id는 스킵 (중복 방지)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

ROOT       = Path(__file__).parent.parent
DB_DIR     = ROOT / "chroma_db"
PDF_DIR    = ROOT / "cases" / "court"
API_DIR    = ROOT / "cases" / "court_api"
CACHE_DIR  = ROOT / "cache"

COLLECTION  = "court_cases"
EMBED_MODEL = "text-embedding-3-small"
BATCH_SIZE  = 50


def _get_collection():
    import os
    client = chromadb.PersistentClient(path=str(DB_DIR))
    ef = OpenAIEmbeddingFunction(
        api_key=os.environ["OPENAI_API_KEY"],
        model_name=EMBED_MODEL,
    )
    return client.get_or_create_collection(
        name=COLLECTION,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def _load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_pdf_doc(f: Path) -> dict | None:
    """PDF 추출본 + bravo 캐시 병합."""
    data = _load_json(f)
    if not data:
        return None

    case_id  = f.stem
    meta_ext = data

    # bravo 캐시 로드
    cache_base = CACHE_DIR / case_id
    narrative  = _load_json(cache_base / "narrative.json") or {}
    issue_log  = _load_json(cache_base / "issue_logic.json") or {}
    meta_cache = _load_json(cache_base / "metadata.json") or {}

    # 임베딩 텍스트 조합
    parts = []

    court    = meta_cache.get("court", meta_ext.get("court", ""))
    case_no  = meta_cache.get("case_no", meta_ext.get("case_no", ""))
    year     = meta_ext.get("year", "")
    case_type = meta_ext.get("case_type", "")

    parts.append(f"[법원: {court}] [사건번호: {case_no}] [유형: {case_type}]")

    fact = narrative.get("fact_summary", "")
    if fact:
        parts.append(fact[:600])

    conflicts = narrative.get("core_conflicts", [])
    if conflicts:
        parts.append("핵심쟁점: " + " / ".join(conflicts[:5]))

    # issue_logic_chains에서 issue 목록 추출
    chains = []
    if isinstance(issue_log, dict):
        chains = issue_log.get("issue_logic_chains", [])
    elif isinstance(issue_log, list):
        chains = issue_log

    if chains:
        issues = [c.get("issue", "") for c in chains[:5] if isinstance(c, dict)]
        parts.append("쟁점: " + " | ".join(i for i in issues if i))

    text = " ".join(p.strip() for p in parts if p.strip())
    if not text:
        return None

    return {
        "id": f"pdf_{case_id}",
        "text": text,
        "meta": {
            "source":     "pdf",
            "case_id":    case_id,
            "court":      court,
            "case_no":    case_no,
            "year":       year,
            "case_type":  case_type,
            "has_cache":  str(cache_base.exists()),
        },
    }


def _build_api_doc(f: Path) -> dict | None:
    """DRF API 수집본 — PrecService 구조 지원 + bravo 캐시 병합."""
    raw = _load_json(f)
    if not raw:
        return None

    # DRF API 응답은 {"PrecService": {...}} 구조
    data = raw.get("PrecService", raw)

    def clean(s: str) -> str:
        return s.replace("<br/>", " ").replace("<br>", " ").strip() if s else ""

    case_id  = f"api_{f.stem}"
    court    = clean(data.get("법원명", ""))
    case_no  = clean(data.get("사건번호", ""))
    case_name = clean(data.get("사건명", ""))
    keyword_match = raw.get("keyword_match", "")

    parts = [
        f"[법원: {court}]",
        f"[사건번호: {case_no}]",
        f"[사건명: {case_name}]",
    ]

    if data.get("판시사항"):
        parts.append(clean(data["판시사항"])[:600])

    if data.get("판결요지"):
        parts.append(clean(data["판결요지"])[:600])

    if data.get("참조조문"):
        parts.append(clean(data["참조조문"])[:200])

    # bravo 캐시 활용 (파이프라인 완료된 경우)
    cache_base = CACHE_DIR / case_id
    narrative  = _load_json(cache_base / "narrative.json") or {}
    issue_log  = _load_json(cache_base / "issue_logic.json") or {}

    if narrative.get("fact_summary"):
        parts.append(narrative["fact_summary"][:600])

    if narrative.get("core_conflicts"):
        parts.append("핵심쟁점: " + " / ".join(narrative["core_conflicts"][:5]))

    chains = issue_log.get("issue_logic_chains", []) if isinstance(issue_log, dict) else []
    if chains:
        issues = [c.get("issue", "") for c in chains[:5] if isinstance(c, dict)]
        parts.append("쟁점: " + " | ".join(i for i in issues if i))

    text = " ".join(p.strip() for p in parts if p.strip())
    if not text.strip():
        return None

    return {
        "id": case_id,
        "text": text,
        "meta": {
            "source":        "api",
            "case_id":       case_id,
            "court":         court,
            "case_no":       case_no,
            "case_name":     case_name,
            "decision_type": clean(data.get("판결유형", "")),
            "keyword_match": keyword_match,
            "has_cache":     str(cache_base.exists()),
        },
    }


def embed_batch(col, docs: list[dict], force: bool = False) -> int:
    """force=True면 기존 항목 삭제 후 재삽입 (갱신용)."""
    if not docs:
        return 0
    ids = [d["id"] for d in docs]
    if force:
        existing = set(col.get(ids=ids, include=[])["ids"])
        if existing:
            col.delete(ids=list(existing))
        new_docs = docs
    else:
        existing = set(col.get(ids=ids, include=[])["ids"])
        new_docs = [d for d in docs if d["id"] not in existing]
    if not new_docs:
        return 0
    col.add(
        ids       = [d["id"]   for d in new_docs],
        documents = [d["text"] for d in new_docs],
        metadatas = [d["meta"] for d in new_docs],
    )
    return len(new_docs)


def run(refresh_api: bool = False) -> None:
    """
    refresh_api=True: 기존 api_ 항목 삭제 후 bravo 캐시 포함 버전으로 재삽입.
    PDF 항목은 이미 bravo 캐시 포함 버전이므로 스킵(중복 방지).
    """
    col = _get_collection()
    print(f"=== court_cases 벡터 DB 빌드 ===")
    print(f"기존 항목: {col.count()}")
    if refresh_api:
        print("모드: API 항목 강제 갱신 (삭제 후 재삽입)")

    total_new = 0
    batch: list[dict] = []

    def flush(force: bool = False):
        nonlocal total_new
        n = embed_batch(col, batch, force=force)
        total_new += n
        batch.clear()

    # 1. PDF 추출본 — 이미 bravo 캐시 포함 버전으로 DB에 있음 → 스킵
    pdf_files = sorted(PDF_DIR.glob("*.json")) if PDF_DIR.exists() else []
    print(f"\nPDF 추출본: {len(pdf_files)}건 (기존 유지)")
    if not refresh_api:
        for f in pdf_files:
            doc = _build_pdf_doc(f)
            if doc:
                batch.append(doc)
            if len(batch) >= BATCH_SIZE:
                flush()

    # 2. DRF API 수집본 — bravo 완료 후 narrative/issue_logic 포함 재빌드
    api_files = sorted(API_DIR.glob("*.json")) if API_DIR.exists() else []
    print(f"DRF API 수집본: {len(api_files)}건")
    for f in api_files:
        doc = _build_api_doc(f)
        if doc:
            batch.append(doc)
        if len(batch) >= BATCH_SIZE:
            flush(force=refresh_api)

    if batch:
        flush(force=refresh_api)

    print(f"\n완료 — 신규/갱신 {total_new}건")
    print(f"   총 컬렉션 크기: {col.count()}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-api", action="store_true",
                        help="기존 api_ 항목 삭제 후 bravo 캐시 포함 버전으로 재삽입")
    args = parser.parse_args()
    run(refresh_api=args.refresh_api)


if __name__ == "__main__":
    run()
