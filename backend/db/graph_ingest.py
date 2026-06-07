# db/graph_ingest.py
"""
cache/ 폴더의 270건 판례 분석 결과를 Neo4j 지식 그래프에 일괄 적재합니다.

노드: Case · IssueChain · Statute · Keyword
임베딩: OpenAI text-embedding-3-small (1536-dim) — issue + fact_summary
MERGE 패턴으로 재실행 시 중복 없이 업서트됩니다.
"""

import hashlib
import json
import os
from pathlib import Path

import openai
from dotenv import load_dotenv
from neo4j import GraphDatabase

from db.graph_schema import init_schema

load_dotenv()

CACHE_ROOT = Path(__file__).parent.parent / "cache"
EMBED_MODEL = "text-embedding-3-small"
EMBED_BATCH = 256          # OpenAI 단일 요청 최대 입력 수
FACT_SUMMARY_MAX = 500     # Case 노드에 저장할 fact_summary 최대 길이


# ─────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────

def _uid(case_id: str, issue_hash: str) -> str:
    """판례 + 쟁점 조합으로 전역 고유 uid 생성 (충돌 방지)"""
    return f"{case_id}:{issue_hash}"


def _statute_id(name: str, provision: str) -> str:
    return hashlib.sha256(f"{name}|{provision}".encode()).hexdigest()[:16]


# ─────────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────────

def load_all_cases() -> list[dict]:
    """캐시 폴더에서 narrative + issue_logic이 모두 있는 판례만 로드"""
    cases = []
    for d in CACHE_ROOT.iterdir():
        if not d.is_dir():
            continue
        required = ["metadata.json", "issue_logic.json", "narrative.json"]
        if not all((d / f).exists() for f in required):
            continue

        case = {
            "case_id": d.name,
            "metadata":      json.loads((d / "metadata.json").read_text(encoding="utf-8")),
            "issue_logic":   json.loads((d / "issue_logic.json").read_text(encoding="utf-8")),
            "narrative":     json.loads((d / "narrative.json").read_text(encoding="utf-8")),
            "keyword_cluster": json.loads((d / "keyword_cluster.json").read_text(encoding="utf-8"))
                               if (d / "keyword_cluster.json").exists() else {},
        }
        cases.append(case)
    return cases


# ─────────────────────────────────────────────
# 임베딩
# ─────────────────────────────────────────────

def batch_embed(texts: list[str], client: openai.OpenAI) -> list[list[float]]:
    """텍스트 리스트를 배치 단위로 임베딩 (빈 문자열은 플레이스홀더로 대체)"""
    texts = [t if t.strip() else "(내용 없음)" for t in texts]
    results = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        resp.data.sort(key=lambda x: x.index)
        results.extend([r.embedding for r in resp.data])
        print(f"  embedding {min(i + EMBED_BATCH, len(texts))}/{len(texts)}")
    return results


def build_embed_inputs(cases: list[dict]) -> tuple[dict, dict]:
    """
    임베딩 대상 텍스트를 수집합니다.
    Returns:
        uid_to_issue: {uid: issue_text}   — IssueChain 임베딩용
        cid_to_fact:  {case_id: fact}     — Case 내러티브 임베딩용
    """
    uid_to_issue: dict[str, str] = {}
    cid_to_fact: dict[str, str] = {}

    for case in cases:
        case_id = case["case_id"]
        cid_to_fact[case_id] = case["narrative"].get("fact_summary", "")[:FACT_SUMMARY_MAX]

        for chain in case["issue_logic"].get("issue_logic_chains", []):
            orig_uid = chain.get("uid") or hashlib.sha256(chain["issue"].encode()).hexdigest()[:12]
            uid = _uid(case_id, orig_uid)
            uid_to_issue[uid] = chain.get("issue", "")

    return uid_to_issue, cid_to_fact


# ─────────────────────────────────────────────
# Neo4j 적재
# ─────────────────────────────────────────────

def ingest_case(
    session,
    case: dict,
    uid_to_embedding: dict[str, list[float]],
    cid_to_embedding: dict[str, list[float]],
) -> None:
    meta     = case["metadata"]
    narrative = case["narrative"]
    issue_logic = case["issue_logic"]
    kw_cluster  = case["keyword_cluster"]
    case_id     = case["case_id"]

    # ── 1) Case 노드 ─────────────────────────────
    session.run(
        """
        MERGE (c:Case {case_id: $case_id})
        SET c.case_number       = $case_number,
            c.court_name        = $court_name,
            c.judgment_date     = $judgment_date,
            c.plaintiff         = $plaintiff,
            c.defendant         = $defendant,
            c.conclusion        = $conclusion,
            c.fact_summary      = $fact_summary,
            c.narrative_embedding = $narrative_embedding
        """,
        {
            "case_id":            case_id,
            "case_number":        meta.get("case_number", ""),
            "court_name":         meta.get("court_name", ""),
            "judgment_date":      meta.get("judgment_date", ""),
            "plaintiff":          meta.get("plaintiff", ""),
            "defendant":          meta.get("defendant", ""),
            "conclusion":         meta.get("conclusion", ""),
            "fact_summary":       narrative.get("fact_summary", "")[:FACT_SUMMARY_MAX],
            "narrative_embedding": cid_to_embedding.get(case_id, []),
        },
    )

    # ── 2) IssueChain 노드 + HAS_ISSUE 엣지 ──────
    for chain in issue_logic.get("issue_logic_chains", []):
        orig_uid = chain.get("uid") or hashlib.sha256(chain["issue"].encode()).hexdigest()[:12]
        uid = _uid(case_id, orig_uid)

        session.run(
            """
            MERGE (i:IssueChain {uid: $uid})
            SET i.issue           = $issue,
                i.premise         = $premise,
                i.evidence        = $evidence,
                i.rule            = $rule,
                i.application     = $application,
                i.inference       = $inference,
                i.mini_conclusion = $mini_conclusion,
                i.embedding       = $embedding
            WITH i
            MATCH (c:Case {case_id: $case_id})
            MERGE (c)-[:HAS_ISSUE]->(i)
            """,
            {
                "uid":            uid,
                "issue":          chain.get("issue", ""),
                "premise":        chain.get("premise", ""),
                "evidence":       chain.get("evidence", ""),
                "rule":           chain.get("rule", ""),
                "application":    chain.get("application", ""),
                "inference":      chain.get("inference", ""),
                "mini_conclusion":chain.get("mini_conclusion", ""),
                "embedding":      uid_to_embedding.get(uid, []),
                "case_id":        case_id,
            },
        )

        # ── 3) Statute 노드 + CITES_STATUTE 엣지 ──
        for cit in chain.get("citations", []):
            if cit.get("type") != "statute":
                continue
            sid = _statute_id(cit.get("name", ""), cit.get("provision", ""))
            session.run(
                """
                MERGE (s:Statute {id: $id})
                SET s.name = $name, s.provision = $provision
                WITH s
                MATCH (i:IssueChain {uid: $uid})
                MERGE (i)-[:CITES_STATUTE]->(s)
                """,
                {
                    "id":        sid,
                    "name":      cit.get("name", ""),
                    "provision": cit.get("provision", ""),
                    "uid":       uid,
                },
            )

    # ── 4) Keyword 노드 + HAS_KEYWORD 엣지 ────────
    for kw in kw_cluster.get("clusters", {}).keys():
        session.run(
            """
            MERGE (k:Keyword {text: $text})
            WITH k
            MATCH (c:Case {case_id: $case_id})
            MERGE (c)-[:HAS_KEYWORD]->(k)
            """,
            {"text": kw, "case_id": case_id},
        )


# ─────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────

def run_ingest() -> None:
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    oai_client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    print("[1/4] 스키마 초기화")
    init_schema(driver)

    print("[2/4] 캐시에서 판례 로드")
    cases = load_all_cases()
    print(f"  → {len(cases)}건 로드 완료")

    print("[3/4] 임베딩 생성")
    uid_to_issue, cid_to_fact = build_embed_inputs(cases)

    issue_uids   = list(uid_to_issue.keys())
    issue_texts  = [uid_to_issue[u] for u in issue_uids]
    issue_embeds = batch_embed(issue_texts, oai_client)
    uid_to_embedding = dict(zip(issue_uids, issue_embeds))

    case_ids    = list(cid_to_fact.keys())
    fact_texts  = [cid_to_fact[c] for c in case_ids]
    fact_embeds = batch_embed(fact_texts, oai_client)
    cid_to_embedding = dict(zip(case_ids, fact_embeds))

    print(f"  → IssueChain {len(uid_to_embedding)}개, Case {len(cid_to_embedding)}개 임베딩 완료")

    print("[4/4] Neo4j 적재 중")
    with driver.session() as session:
        for i, case in enumerate(cases):
            ingest_case(session, case, uid_to_embedding, cid_to_embedding)
            if (i + 1) % 20 == 0 or (i + 1) == len(cases):
                print(f"  → {i + 1}/{len(cases)} 적재 완료")

    driver.close()
    print("\n[완료] 전체 적재 완료")


if __name__ == "__main__":
    run_ingest()
