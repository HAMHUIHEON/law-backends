"""
scripts/embed_pdf_cases.py
판례 케이스를 Chroma 'pdf_court_cases' 컬렉션에 임베딩.

임베딩 소스 우선순위:
  1. cache/{case_id}/narrative.json — bravo 파이프라인 구조화 요약 (최고품질)
  2. cache/{case_id}/issue_logic.json — 쟁점·논거 텍스트
  3. cache/{case_id}/raw.json — 원문 단락
  4. uploads/ 또는 CASE/ PDF 원문 텍스트 (fallback)

사용:
  python scripts/embed_pdf_cases.py                      # cache 우선, uploads/ fallback
  python scripts/embed_pdf_cases.py --cache-dir ../cache  # cache 경로 명시
  python scripts/embed_pdf_cases.py --reset              # 컬렉션 삭제 후 재생성
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

CHROMA_DIR = Path(os.environ.get("CHROMA_DIR", str(ROOT.parent / "vector_db" / "chroma")))
COLLECTION_NAME = "pdf_court_cases"
BATCH = 30
EMBED_MODEL = "text-embedding-3-small"

COURT_PATTERNS = [
    (r"대법원", "대법원"),
    (r"서울고등법원|서울고법", "서울고등법원"),
    (r"수원고등법원", "수원고등법원"),
    (r"광주고등법원", "광주고등법원"),
    (r"대구고등법원", "대구고등법원"),
    (r"서울행정법원", "서울행정법원"),
    (r"서울중앙지방법원", "서울중앙지방법원"),
    (r"수원지방법원", "수원지방법원"),
    (r"대전지방법원", "대전지방법원"),
    (r"인천지방법원", "인천지방법원"),
    (r"대구지방법원", "대구지방법원"),
    (r"광주지방법원", "광주지방법원"),
]


def _parse_meta(stem: str) -> dict:
    court = "불명"
    for pat, name in COURT_PATTERNS:
        if re.search(pat, stem):
            court = name
            break
    case_no = re.sub(r"^[^_]+_", "", stem)
    tax_type = "행정" if re.search(r"두\d+", case_no) else "형사"
    return {"court": court, "case_no": case_no, "case_id": stem, "tax_type": tax_type, "source": "cache"}


def _safe_str(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return " ".join(_safe_str(x) for x in v if x)
    if isinstance(v, dict):
        return " ".join(_safe_str(x) for x in v.values() if x)
    return str(v) if v else ""


def _text_from_narrative(case_dir: Path) -> str:
    """narrative.json에서 고품질 요약 텍스트 추출."""
    fpath = case_dir / "narrative.json"
    if not fpath.exists():
        return ""
    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        parts = []
        for key in ["fact_summary", "legal_context", "court_reasoning", "conclusion",
                    "plaintiff_arguments", "defendant_arguments"]:
            v = data.get(key)
            if v:
                parts.append(f"[{key}] {_safe_str(v)}")
        return "\n".join(parts)[:4000]
    except Exception:
        return ""


def _text_from_issue_logic(case_dir: Path) -> str:
    """issue_logic.json에서 쟁점+논거 텍스트 추출."""
    fpath = case_dir / "issue_logic.json"
    if not fpath.exists():
        return ""
    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        parts = []
        outline = data.get("global_outline")
        if outline:
            parts.append(f"[개요] {_safe_str(outline)[:500]}")
        issues = data.get("main_issues") or []
        for i in issues[:3]:
            parts.append(f"[쟁점] {_safe_str(i)[:300]}")
        chains = data.get("issue_logic_chains") or []
        for ch in chains[:3]:
            issue = _safe_str(ch.get("issue", ""))[:200]
            premise = _safe_str(ch.get("premise", ""))[:200]
            if issue:
                parts.append(f"[논거] {issue}: {premise}")
        return "\n".join(parts)[:4000]
    except Exception:
        return ""


def _text_from_raw(case_dir: Path) -> str:
    """raw.json 또는 paragraphs.json에서 원문 텍스트 추출."""
    for fname in ["paragraphs.json", "raw.json"]:
        fpath = case_dir / fname
        if not fpath.exists():
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                texts = []
                for item in data[:20]:
                    if isinstance(item, dict):
                        t = item.get("text") or item.get("content") or ""
                    else:
                        t = str(item)
                    if t.strip():
                        texts.append(t.strip()[:200])
                text = "\n".join(texts)
                if text:
                    return text[:4000]
            elif isinstance(data, dict):
                return _safe_str(data)[:4000]
        except Exception:
            continue
    return ""


def _text_from_pdf(pdf_path: Path) -> str:
    """pypdf로 PDF 텍스트 추출 (fallback)."""
    if not pdf_path.exists():
        return ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        pages = []
        for page in reader.pages[:8]:
            t = page.extract_text() or ""
            if t.strip():
                pages.append(t.strip())
        return "\n".join(pages)[:4000]
    except Exception as e:
        print(f"  [WARN] PDF 추출 실패 {pdf_path.name}: {e}")
        return ""


def _get_case_text(case_id: str, cache_dir: Path, pdf_dirs: list[Path]) -> tuple[str, str]:
    """
    Returns (text, source_label).
    source_label: 'narrative' | 'issue_logic' | 'raw' | 'pdf' | ''
    """
    case_dir = cache_dir / case_id
    if case_dir.exists():
        text = _text_from_narrative(case_dir)
        if text.strip():
            return text, "narrative"
        text = _text_from_issue_logic(case_dir)
        if text.strip():
            return text, "issue_logic"
        text = _text_from_raw(case_dir)
        if text.strip():
            return text, "raw"

    # fallback: PDF
    for pdf_dir in pdf_dirs:
        pdf_path = pdf_dir / f"{case_id}.pdf"
        text = _text_from_pdf(pdf_path)
        if text.strip():
            return text, "pdf"

    return "", ""


def _embed_batch(texts: list[str], client) -> list[list[float]]:
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in resp.data]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", default=None, help="cache 디렉토리 경로")
    parser.add_argument("--pdf-dirs", nargs="+", default=["uploads"], help="PDF 디렉토리 목록 (fallback)")
    parser.add_argument("--reset", action="store_true", help="컬렉션 삭제 후 재생성")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir) if args.cache_dir else ROOT / "cache"
    pdf_dirs = [ROOT / d for d in args.pdf_dirs]

    import chromadb
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        env_file = ROOT.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
    if not api_key:
        print("[embed_pdf] ERROR: OPENAI_API_KEY 없음")
        sys.exit(1)

    oai = OpenAI(api_key=api_key)

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    if args.reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"[embed_pdf] 기존 {COLLECTION_NAME} 삭제 완료")
        except Exception:
            pass

    try:
        col = client.get_collection(COLLECTION_NAME)
        print(f"[embed_pdf] 기존 컬렉션 사용: {col.count()}건 존재")
    except Exception:
        col = client.create_collection(
            COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"[embed_pdf] 신규 컬렉션 생성: {COLLECTION_NAME}")

    existing = set(col.get(limit=max(col.count(), 1))["ids"]) if col.count() > 0 else set()
    print(f"[embed_pdf] 기존 처리 건수: {len(existing)}")

    # 케이스 ID 수집: cache 폴더 + pdf 파일 stems
    case_ids: set[str] = set()
    if cache_dir.exists():
        for p in cache_dir.iterdir():
            if p.is_dir() and re.match(r"[가-힣]+_\d+", p.name):
                case_ids.add(p.name)
        print(f"[embed_pdf] cache 케이스: {len(case_ids)}건")

    for pdf_dir in pdf_dirs:
        if pdf_dir.exists():
            for p in pdf_dir.glob("*.pdf"):
                case_ids.add(p.stem)
            print(f"[embed_pdf] {pdf_dir.name} PDF: {len(pdf_dir.glob('*.pdf'))}건 추가")

    print(f"[embed_pdf] 총 케이스 (중복 제거): {len(case_ids)}건")

    batch_ids, batch_docs, batch_metas = [], [], []
    added = 0
    skipped = 0
    no_text = 0

    for case_id in sorted(case_ids):
        doc_id = f"pdf_{case_id}"
        if doc_id in existing:
            skipped += 1
            continue

        text, source = _get_case_text(case_id, cache_dir, pdf_dirs)
        if not text.strip():
            no_text += 1
            continue

        meta = _parse_meta(case_id)
        meta["text_source"] = source
        doc = f"[{case_id}] {text}"
        batch_ids.append(doc_id)
        batch_docs.append(doc)
        batch_metas.append(meta)

        if len(batch_ids) >= BATCH:
            print(f"[embed_pdf] 배치 임베딩 {len(batch_ids)}건... (현재 {added + len(batch_ids)}건 처리)")
            embs = _embed_batch(batch_docs, oai)
            col.upsert(ids=batch_ids, embeddings=embs, documents=batch_docs, metadatas=batch_metas)
            added += len(batch_ids)
            batch_ids, batch_docs, batch_metas = [], [], []

    if batch_ids:
        print(f"[embed_pdf] 마지막 배치 {len(batch_ids)}건...")
        embs = _embed_batch(batch_docs, oai)
        col.upsert(ids=batch_ids, embeddings=embs, documents=batch_docs, metadatas=batch_metas)
        added += len(batch_ids)

    print(
        f"\n[embed_pdf] 완료\n"
        f"  추가: {added}건\n"
        f"  스킵(기존): {skipped}건\n"
        f"  텍스트 없음: {no_text}건\n"
        f"  최종 컬렉션: {col.count()}건"
    )


if __name__ == "__main__":
    main()
