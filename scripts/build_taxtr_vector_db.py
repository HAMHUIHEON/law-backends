"""
조세심판원 재결례 벡터 DB 구축 — Chroma + text-embedding-3-small

대상: cases/taxtr/{dem_no}.json
임베딩 텍스트: [세목] [결정유형] 제목 + 결정요지 (요약)
컬렉션: taxtr_cases
저장 위치: vector_db/chroma (법령 조문 DB와 동일 경로, 컬렉션 분리)

실행:
  python scripts/build_taxtr_vector_db.py           # 전체 구축
  python scripts/build_taxtr_vector_db.py --reset   # 컬렉션 초기화 후 재구축
  python scripts/build_taxtr_vector_db.py --wait    # 수집 완료 대기 후 구축
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
CASES_DIR  = ROOT / "cases" / "taxtr"
CHROMA_DIR = ROOT / "vector_db" / "chroma"
LOG_FILE   = ROOT / "cases" / "taxtr_collect.log"

OPENAI_KEY    = os.getenv("OPENAI_API_KEY", "")
COLLECTION    = "taxtr_cases"
BATCH_SIZE    = 100
MIN_TEXT_LEN  = 20


# ── 수집 완료 감지 ────────────────────────────────────────────────────────────

def is_collection_done() -> bool:
    """로그 파일에서 '완료' 또는 수집 프로세스 종료 여부 판단."""
    if not LOG_FILE.exists():
        return False
    text = LOG_FILE.read_text(encoding="utf-8", errors="ignore")
    return "완료" in text or "🎉" in text


def wait_for_collection(poll_sec: int = 60) -> None:
    """수집 완료까지 대기."""
    print("⏳ 조세심판원 수집 완료 대기 중...", flush=True)
    while True:
        if is_collection_done():
            print("✅ 수집 완료 감지", flush=True)
            return
        # 현재 수집 건수 표시
        n = len(list(CASES_DIR.glob("*.json"))) if CASES_DIR.exists() else 0
        print(f"   현재 {n}건 수집됨, {poll_sec}초 후 재확인...", flush=True)
        time.sleep(poll_sec)


# ── 텍스트 구성 ───────────────────────────────────────────────────────────────

def _build_doc_text(case: dict) -> str:
    """검색 최적화 텍스트: 세목·유형·제목·요지."""
    parts = []
    if case.get("tax_type"):
        parts.append(f"[세목: {case['tax_type']}]")
    if case.get("decision"):
        parts.append(f"[결정유형: {case['decision']}]")
    if case.get("title"):
        parts.append(case["title"])
    if case.get("summary"):
        parts.append(case["summary"])
    if case.get("related_laws"):
        parts.append(f"관련법령: {case['related_laws']}")
    return "\n".join(parts)


def _build_metadata(case: dict) -> dict:
    """Chroma 메타데이터 — 모든 값은 str/int/float/bool만 허용."""
    return {
        "dem_no":        case.get("dem_no", ""),
        "case_no":       case.get("case_no", ""),
        "decision_date": case.get("decision_date", ""),
        "tax_type":      case.get("tax_type", ""),
        "decision":      case.get("decision", ""),
        "related_laws":  case.get("related_laws", "")[:500],  # 길이 제한
        "title":         case.get("title", "")[:200],
    }


# ── Chroma 클라이언트 ─────────────────────────────────────────────────────────

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
            print("기존 컬렉션 삭제 완료", flush=True)
        except Exception:
            pass

    return client.get_or_create_collection(
        name=COLLECTION,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


# ── 인제스트 ─────────────────────────────────────────────────────────────────

def get_existing_ids(col: chromadb.Collection) -> set[str]:
    """이미 인제스트된 doc_id 집합."""
    try:
        result = col.get(include=[])
        return set(result["ids"])
    except Exception:
        return set()


def run(reset: bool = False) -> None:
    if not CASES_DIR.exists():
        print(f"⛔ 재결례 폴더 없음: {CASES_DIR}", flush=True)
        return

    json_files = sorted(CASES_DIR.glob("*.json"))
    total_files = len(json_files)
    print(f"=== 조세심판원 재결례 벡터 DB 구축 ===", flush=True)
    print(f"대상: {total_files}개 파일\n", flush=True)

    col = get_collection(reset=reset)
    existing_ids = get_existing_ids(col)
    print(f"기존 인제스트 건수: {len(existing_ids)}", flush=True)

    docs, metas, ids = [], [], []
    skipped_dup = 0
    skipped_short = 0
    t0 = time.time()

    def _flush(force: bool = False) -> None:
        nonlocal docs, metas, ids
        if not docs:
            return
        if not force and len(docs) < BATCH_SIZE:
            return
        col.upsert(documents=docs, metadatas=metas, ids=ids)
        docs, metas, ids = [], [], []

    for i, fp in enumerate(json_files, 1):
        try:
            case = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue

        dem_no = case.get("dem_no", fp.stem)
        doc_id = f"taxtr__{dem_no}"

        if doc_id in existing_ids:
            skipped_dup += 1
            continue

        text = _build_doc_text(case)
        if len(text) < MIN_TEXT_LEN:
            skipped_short += 1
            continue

        docs.append(text)
        metas.append(_build_metadata(case))
        ids.append(doc_id)

        if len(docs) >= BATCH_SIZE:
            _flush(force=True)

        if i % 500 == 0:
            elapsed = time.time() - t0
            print(
                f"[{i}/{total_files}] 누적 {len(existing_ids) + i - skipped_dup - skipped_short}건"
                f" | 중복스킵 {skipped_dup} | {elapsed:.0f}s 경과",
                flush=True,
            )

    _flush(force=True)

    elapsed = time.time() - t0
    final_count = col.count()
    print(f"\n🎉 완료 — 컬렉션 총 {final_count}건 / {elapsed:.0f}s", flush=True)
    print(f"   중복 스킵: {skipped_dup}건, 텍스트 부족 스킵: {skipped_short}건", flush=True)
    print(f"   저장 위치: {CHROMA_DIR}", flush=True)


# ── 엔트리 ───────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="조세심판원 재결례 벡터 DB 구축")
    ap.add_argument("--reset", action="store_true", help="컬렉션 초기화 후 재구축")
    ap.add_argument("--wait",  action="store_true", help="수집 완료 대기 후 구축")
    ap.add_argument("--poll",  type=int, default=60, help="대기 폴링 간격(초, 기본 60)")
    args = ap.parse_args()

    if args.wait:
        wait_for_collection(poll_sec=args.poll)

    run(reset=args.reset)


if __name__ == "__main__":
    main()
