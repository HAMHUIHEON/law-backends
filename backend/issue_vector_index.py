import os
import json
import pickle
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI


# -----------------------------------
# ENV / CONFIG
# -----------------------------------

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

client = OpenAI(api_key=OPENAI_API_KEY)

MODEL = "text-embedding-3-small"

CACHE_DIR = Path(__file__).parent / "cache"

INDEX_DIR = Path(__file__).parent / "issue_index"
INDEX_DIR.mkdir(exist_ok=True)

INDEX_FILE = INDEX_DIR / "issue_vectors.pkl"
INDEX_META_FILE = INDEX_DIR / "issue_vectors_meta.json"


# -----------------------------------
# BASIC UTILS
# -----------------------------------

def embed(text: str) -> np.ndarray:
    """
    OpenAI embedding 생성
    """
    text = text.strip()
    if not text:
        raise ValueError("임베딩할 텍스트가 비어 있습니다.")

    res = client.embeddings.create(
        model=MODEL,
        input=text,
    )
    return np.array(res.data[0].embedding, dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """
    cosine similarity
    """
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def load_index() -> List[Dict[str, Any]]:
    """
    기존 인덱스 로드
    """
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "rb") as f:
            return pickle.load(f)
    return []


def save_index(index: List[Dict[str, Any]]) -> None:
    """
    인덱스 저장
    """
    with open(INDEX_FILE, "wb") as f:
        pickle.dump(index, f)


def load_index_meta() -> Dict[str, str]:
    """
    case_id -> file hash 메타 로드
    """
    if INDEX_META_FILE.exists():
        with open(INDEX_META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_index_meta(meta: Dict[str, str]) -> None:
    """
    case_id -> file hash 메타 저장
    """
    with open(INDEX_META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def file_sha256(path: Path) -> str:
    """
    파일 해시 계산
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_get(d: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    """
    중첩 dict 안전 접근
    """
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


# -----------------------------------
# JSON PARSING
# -----------------------------------

def extract_core_issues(data: Dict[str, Any]) -> List[str]:
    """
    executive_summary.executive_summary.core_issues 추출
    """
    issues = safe_get(
        data,
        ["executive_summary", "executive_summary", "core_issues"],
        default=[],
    )
    if not isinstance(issues, list):
        return []
    return [str(x).strip() for x in issues if str(x).strip()]


def extract_issue_logic_chains(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    body.issue_logic.issue_logic_chains 추출
    """
    chains = safe_get(
        data,
        ["body", "issue_logic", "issue_logic_chains"],
        default=[],
    )
    if not isinstance(chains, list):
        return []
    return chains


def extract_issue_statutes_and_context(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    issue_logic_chains 기준으로
    issue -> statutes / citation_texts / retrieval_context
    맵 생성
    """
    chains = extract_issue_logic_chains(data)

    issue_map: Dict[str, Dict[str, Any]] = {}

    for chain in chains:
        issue = str(chain.get("issue", "")).strip()
        if not issue:
            continue

        statutes: List[str] = []
        citation_texts: List[str] = []

        citations = chain.get("citations", [])
        if not isinstance(citations, list):
            citations = []

        for c in citations:
            if not isinstance(c, dict):
                continue
            if c.get("source_type") != "statute":
                continue

            title = str(c.get("title", "")).strip()
            if title:
                statutes.append(title)

            citation_text = str(c.get("citation_text", "")).strip()
            if citation_text:
                citation_texts.append(citation_text)

        # 순서 유지 중복 제거
        dedup_statutes = list(dict.fromkeys(statutes))
        dedup_citation_texts = list(dict.fromkeys(citation_texts))

        rule = str(chain.get("rule", "")).strip()
        application = str(chain.get("application", "")).strip()
        inference = str(chain.get("inference", "")).strip()
        mini_conclusion = str(chain.get("mini_conclusion", "")).strip()

        issue_map[issue] = {
            "statutes": dedup_statutes,
            "citation_texts": dedup_citation_texts,
            "rule": rule,
            "application": application,
            "inference": inference,
            "mini_conclusion": mini_conclusion,
        }

    return issue_map


# -----------------------------------
# MATCHING
# -----------------------------------

def precompute_issue_vectors(issue_logic_issues: List[str]) -> Dict[str, np.ndarray]:
    """
    세부 issue 벡터를 미리 생성
    """
    issue_vecs: Dict[str, np.ndarray] = {}
    for issue in issue_logic_issues:
        issue_vecs[issue] = embed(issue)
    return issue_vecs


def map_core_issue(
    core_issue: str,
    issue_vecs: Dict[str, np.ndarray],
) -> Optional[str]:
    """
    core_issue와 가장 가까운 issue_logic_chain.issue 찾기
    """
    if not issue_vecs:
        return None

    core_vec = embed(core_issue)

    best_issue: Optional[str] = None
    best_score = -1.0

    for issue, vec in issue_vecs.items():
        score = cosine(core_vec, vec)
        if score > best_score:
            best_score = score
            best_issue = issue

    return best_issue


# -----------------------------------
# RETRIEVAL TEXT DESIGN
# -----------------------------------

def truncate_text_list(items: List[str], limit: int = 3) -> List[str]:
    """
    너무 길어지지 않게 앞 일부만 사용
    """
    return items[:limit]


def build_retrieval_text(
    core_issue: str,
    matched_issue: Optional[str],
    statutes: List[str],
    citation_texts: List[str],
    rule: str,
    application: str,
    inference: str,
    mini_conclusion: str,
) -> str:
    """
    검색용 임베딩 텍스트 구성
    """
    parts: List[str] = []

    parts.append(f"상위 쟁점: {core_issue}")

    if matched_issue:
        parts.append(f"세부 쟁점: {matched_issue}")

    if statutes:
        parts.append("관련 법령: " + " / ".join(statutes))

    # citation_text는 너무 길면 오히려 노이즈가 생긴다.
    # 앞부분 일부만 넣는다.
    limited_citations = truncate_text_list(citation_texts, limit=2)
    if limited_citations:
        parts.append("판례 인용 문맥: " + " ".join(limited_citations))

    if rule:
        parts.append(f"법리: {rule}")

    if application:
        parts.append(f"사안 적용: {application}")

    if inference:
        parts.append(f"추론: {inference}")

    if mini_conclusion:
        parts.append(f"소결론: {mini_conclusion}")

    return "\n".join(parts).strip()


# -----------------------------------
# INDEX BUILD
# -----------------------------------

def build_index() -> List[Dict[str, Any]]:
    """
    증분 인덱스 구축
    - 기존 index 유지
    - 변경 없는 case는 skip
    - 변경된 case는 해당 case row 재생성
    """
    index = load_index()
    index_meta = load_index_meta()

    # case_id 단위 재구축을 위해 기존 index를 case_id로 그룹화
    current_index_by_case: Dict[str, List[Dict[str, Any]]] = {}
    for row in index:
        case_id = row["case_id"]
        current_index_by_case.setdefault(case_id, []).append(row)

    updated_cases = 0

    for case_dir in CACHE_DIR.iterdir():
        if not case_dir.is_dir():
            continue

        case_id = case_dir.name
        json_path = case_dir / "export_C_full.json"

        if not json_path.exists():
            continue

        try:
            digest = file_sha256(json_path)
            old_digest = index_meta.get(case_id)

            # 변경 없는 케이스는 skip
            if old_digest == digest:
                continue

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            core_issues = extract_core_issues(data)
            issue_map = extract_issue_statutes_and_context(data)
            logic_issues = list(issue_map.keys())

            if not core_issues:
                print(f"skip: {case_id} - core_issues 없음")
                continue

            # 해당 case 기존 row 삭제
            current_index_by_case.pop(case_id, None)

            # 세부 issue 벡터 선계산
            issue_vecs = precompute_issue_vectors(logic_issues) if logic_issues else {}

            case_rows: List[Dict[str, Any]] = []

            for core_issue in core_issues:
                matched_issue = map_core_issue(core_issue, issue_vecs) if issue_vecs else None

                statutes: List[str] = []
                citation_texts: List[str] = []
                rule = ""
                application = ""
                inference = ""
                mini_conclusion = ""

                if matched_issue:
                    matched = issue_map[matched_issue]
                    statutes = matched["statutes"]
                    citation_texts = matched["citation_texts"]
                    rule = matched["rule"]
                    application = matched["application"]
                    inference = matched["inference"]
                    mini_conclusion = matched["mini_conclusion"]

                retrieval_text = build_retrieval_text(
                    core_issue=core_issue,
                    matched_issue=matched_issue,
                    statutes=statutes,
                    citation_texts=citation_texts,
                    rule=rule,
                    application=application,
                    inference=inference,
                    mini_conclusion=mini_conclusion,
                )

                vec = embed(retrieval_text)

                case_rows.append(
                    {
                        "case_id": case_id,
                        "core_issue": core_issue,
                        "matched_issue": matched_issue,
                        "retrieval_text": retrieval_text,
                        "vector": vec,
                        "statutes": statutes,
                        "citation_texts": citation_texts,
                        "score_hint_rule": rule,
                        "score_hint_application": application,
                        "score_hint_inference": inference,
                        "mini_conclusion": mini_conclusion,
                    }
                )

            current_index_by_case[case_id] = case_rows
            index_meta[case_id] = digest
            updated_cases += 1

            print(f"indexed: {case_id} ({len(case_rows)} issues)")

        except Exception as e:
            print(f"skip: {case_id} - {e}")

    # 평탄화
    rebuilt_index: List[Dict[str, Any]] = []
    for rows in current_index_by_case.values():
        rebuilt_index.extend(rows)

    save_index(rebuilt_index)
    save_index_meta(index_meta)

    print(f"updated cases: {updated_cases}")
    return rebuilt_index


# -----------------------------------
# SEARCH
# -----------------------------------

def search(index: List[Dict[str, Any]], query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    쟁점 / 법령 / 자연어 질문 모두 검색 가능
    """
    query = query.strip()
    if not query:
        return []

    q_vec = embed(query)

    results: List[Dict[str, Any]] = []

    for row in index:
        score = cosine(q_vec, row["vector"])

        results.append(
            {
                "case_id": row["case_id"],
                "core_issue": row["core_issue"],
                "matched_issue": row["matched_issue"],
                "statutes": row["statutes"],
                "citation_texts": row["citation_texts"],
                "mini_conclusion": row.get("mini_conclusion"),
                "score": score,
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# -----------------------------------
# DISPLAY
# -----------------------------------

def print_results(results: List[Dict[str, Any]]) -> None:
    if not results:
        print("\n검색 결과가 없습니다.")
        return

    for i, r in enumerate(results, start=1):
        print(f"\n[{i}] {r['score']:.3f} | {r['case_id']}")
        print(f"core_issue: {r['core_issue']}")

        if r["matched_issue"] and r["matched_issue"] != r["core_issue"]:
            print(f"matched_issue: {r['matched_issue']}")

        if r.get("mini_conclusion"):
            mc = r["mini_conclusion"]
            print("mini_conclusion:")
            print(f"  → {mc[:300]}..." if len(mc) > 300 else f"  → {mc}")

        if r["statutes"]:
            print("statutes:")
            for s in r["statutes"][:5]:
                print(f"  - {s}")

        if r["citation_texts"]:
            print("citation_text:")
            for c in r["citation_texts"][:2]:
                print(f"  - {c[:200]}..." if len(c) > 200 else f"  - {c}")


# -----------------------------------
# MAIN
# -----------------------------------

def main() -> None:
    print("building / updating index...")
    index = build_index()
    print(f"total indexed issues: {len(index)}")

    while True:
        q = input("\nquery (종료: exit): ").strip()

        if q.lower() in {"exit", "quit"}:
            print("종료합니다.")
            break

        results = search(index, q, top_k=5)
        print_results(results)


if __name__ == "__main__":
    main()