#ITCL_integrated/ingest.py
from __future__ import annotations
from neo4j import GraphDatabase
import os,json
from typing import Optional
import dotenv
import neo4j

dotenv.load_dotenv()
import re
import hashlib

#.\neo4j.bat console
URI = os.getenv("NEO4J_URI", "neo4j+s://3dfa7316.databases.neo4j.io")
AUTH = ("neo4j", os.getenv("NEO4J_PASSWORD", "password"))

driver = neo4j.GraphDatabase.driver(URI, auth=AUTH)

# =========================================================
# Constraints (참고 - Neo4j에서 1회 실행)
# =========================================================
"""
DROP CONSTRAINT integrated_semantic_issue_key IF EXISTS;

// IntegratedSnapshot: 세트 앵커
CREATE CONSTRAINT integrated_snapshot_key IF NOT EXISTS
FOR (s:IntegratedSnapshot)
REQUIRE (s.scope, s.set_key) IS UNIQUE;

// IntegratedChapter: 세트+챕터 앵커
CREATE CONSTRAINT integrated_chapter_key IF NOT EXISTS
FOR (ic:IntegratedChapter)
REQUIRE (ic.scope, ic.set_key, ic.chapter_id) IS UNIQUE;

// Integrated SemanticIssue: 세트+issue_id 앵커
CREATE CONSTRAINT integrated_semantic_issue_key IF NOT EXISTS
FOR (s:SemanticIssue)
REQUIRE (s.scope, s.set_key, s.id) IS UNIQUE;

// Integrated ReasoningIssue: 세트+id 앵커 (id는 stable hash)
CREATE CONSTRAINT integrated_reasoning_issue_key IF NOT EXISTS
FOR (r:ReasoningIssue)
REQUIRE (r.scope, r.set_key, r.id) IS UNIQUE;

// Alignment 관계는 관계라 제약 불가. 필요하면 인덱스/쿼리로 검증.
"""

# =========================================================
# Helpers
# =========================================================

SET_KEY_RE = re.compile(
    r"^LAW_(?P<law>[^_]+_[^_]+)__DECREE_(?P<decree>[^_]+_[^_]+)__RULE_(?P<rule>[^_]+_[^_]+)$"
)

def parse_set_key(set_key: str) -> tuple[str, str, str]:
    """
    set_key 예:
      LAW_20171219_15221__DECREE_20171219_15222__RULE_20171219_15223
    반환:
      (law_vkey, decree_vkey, rule_vkey)
    """
    m = SET_KEY_RE.match(set_key)
    if not m:
        raise ValueError(f"[INGEST BLOCKED] invalid set_key format: {set_key}")
    return (m.group("law"), m.group("decree"), m.group("rule"))

def infer_set_key_from_reasoning_path(reasoning_enriched_path: str) -> str:
    """
    reasoning_enriched_path가 보통:
      cache/{prefix}/{set_key}/05_reasoning_enriched.json
    이 구조일 때 set_key 자동 추출.
    """
    parts = reasoning_enriched_path.replace("\\", "/").split("/")
    if len(parts) < 2:
        raise ValueError(f"[INGEST BLOCKED] cannot infer set_key from path: {reasoning_enriched_path}")

    # 가장 안전: 파일명 직전 폴더
    # .../{set_key}/05_reasoning_enriched.json
    set_key = parts[-2]
    # set_key 검증
    parse_set_key(set_key)
    return set_key

def stable_reasoning_issue_id(chapter_id: str, issue_title: str) -> str:
    """
    Python hash()는 런마다 달라질 수 있어서(시드) DB 키로 쓰면 지옥.
    sha256으로 stable id 생성.
    """
    h = hashlib.sha256(issue_title.strip().encode("utf-8")).hexdigest()[:12]
    return f"{chapter_id}_REASON_{h}"

# =========================================================
# Context
# =========================================================

class IntegratedIngestContext:
    def __init__(
        self,
        semantic_dict: dict,
        reasoning_dict: dict,
        reasoning_enriched_path: str,
        prefix: str = "ITCL_integrated",
        set_key: str | None = None,   # ✅ 선택: 없으면 reasoning_enriched_path에서 자동 추출
    ):
        self.semantic_dict = semantic_dict
        self.reasoning_dict = reasoning_dict
        self.reasoning_enriched_path = reasoning_enriched_path
        self.prefix = prefix
        self.set_key = set_key

# =========================================================
# 0) Snapshot ingest (세트 앵커)
# =========================================================

def ingest_integrated_snapshot(
    tx,
    *,
    set_key: str,
    promulgated_at: str,
    effective_at: str,
    valid_from: str,
    valid_to: Optional[str] = None,
):
    law_vkey, decree_vkey, rule_vkey = parse_set_key(set_key)

    tx.run(
        """
        MERGE (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
        SET s.law_version_key    = $law_vkey,
            s.decree_version_key = $decree_vkey,
            s.rule_version_key   = $rule_vkey,
            s.promulgated_at     = $promulgated_at,
            s.effective_at       = $effective_at,
            s.valid_from         = $valid_from,
            s.valid_to           = $valid_to
        """,
        set_key=set_key,
        law_vkey=law_vkey,
        decree_vkey=decree_vkey,
        rule_vkey=rule_vkey,
        promulgated_at=promulgated_at,
        effective_at=effective_at,
        valid_from=valid_from,
        valid_to=valid_to,
    )

"""
“특정 기준일에 유효한 통합 세트” 질의 가능
MATCH (s:IntegratedSnapshot)
WHERE s.valid_from <= date("2017-12-19")
  AND (s.valid_to IS NULL OR s.valid_to > date("2017-12-19"))
RETURN s
-> 이건 아직 no records인데. 이게 되려면 어떻게 해야하는지. 써주라.

"""

# =========================================================
# 1) IntegratedChapter ingest (세트+챕터 앵커)
#    - scope="INTEGRATED"
#    - set_key 필수
# =========================================================

def ingest_integrated_chapters(tx, *, set_key: str, semantic_dict: dict):
    tx.run(
        """
        MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
        WITH s
        UNWIND $rows AS row
        MERGE (ic:IntegratedChapter {scope:"INTEGRATED", set_key:$set_key, chapter_id:row.chapter_id})
        SET ic.name = row.chapter_name
        MERGE (s)-[:HAS_INTEGRATED_CHAPTER]->(ic)
        """,
        set_key=set_key,
        rows=[
            {"chapter_id": cid, "chapter_name": ch.get("chapter_name")}
            for cid, ch in semantic_dict.items()
        ],
    )

# =========================================================
# 2) IntegratedChapter -> Source Chapter linking
#    - norm 인제스트가 Chapter(scope, version_key, id)로 바뀌었으니
#      여기서도 반드시 version_key로 매칭해야 함.
# =========================================================
"""
Law (scope=LAW, id=국제조세조정법)
└─ HAS_VERSION
   └─ LawVersion (scope=LAW, version_key=20171219_15221)
      └─ HAS_CHAPTER
         └─ Chapter (scope=LAW, version_key=20171219_15221, id=CH_6)

IntegratedSnapshot (scope=INTEGRATED, set_key=LAW_20171219_15221__DECREE_...__RULE_...)
└─ HAS_INTEGRATED_CHAPTER
   └─ IntegratedChapter (scope=INTEGRATED, set_key=..., chapter_id=CH_6)

검증 쿼리
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic)
      -[:DERIVED_FROM]->(c:Chapter)
RETURN
  ic.chapter_id,
  c.scope,
  c.version_key,
  c.id
ORDER BY ic.chapter_id, c.scope;

"""
def link_integrated_to_source_chapters(tx, *, set_key: str, chapter_id: str):
    law_vkey, decree_vkey, rule_vkey = parse_set_key(set_key)

    tx.run(
        """
        MATCH (ic:IntegratedChapter {scope:"INTEGRATED", set_key:$set_key, chapter_id:$cid})

        // LAW
        OPTIONAL MATCH (c_law:Chapter {scope:"LAW", version_key:$law_vkey, id:$cid})
        FOREACH (_ IN CASE WHEN c_law IS NULL THEN [] ELSE [1] END |
        MERGE (ic)-[:DERIVED_FROM {source_scope:"LAW"}]->(c_law)
        )
        WITH ic

        // DECREE
        OPTIONAL MATCH (c_dec:Chapter {scope:"DECREE", version_key:$decree_vkey, id:$cid})
        FOREACH (_ IN CASE WHEN c_dec IS NULL THEN [] ELSE [1] END |
        MERGE (ic)-[:DERIVED_FROM {source_scope:"DECREE"}]->(c_dec)
        )
        WITH ic

        // RULE
        OPTIONAL MATCH (c_rule:Chapter {scope:"RULE", version_key:$rule_vkey, id:$cid})
        FOREACH (_ IN CASE WHEN c_rule IS NULL THEN [] ELSE [1] END |
        MERGE (ic)-[:DERIVED_FROM {source_scope:"RULE"}]->(c_rule)
        )
        """,
        set_key=set_key,
        cid=chapter_id,
        law_vkey=law_vkey,
        decree_vkey=decree_vkey,
        rule_vkey=rule_vkey,
    )

def link_all_integrated_chapters(tx, *, set_key: str, semantic_dict: dict):
    for cid in semantic_dict.keys():
        link_integrated_to_source_chapters(tx, set_key=set_key, chapter_id=cid)

# =========================================================
# 3) Integrated Semantic ingest
#    - SemanticIssue도 set_key 없으면 충돌남(구법/현행)
# =========================================================

def ingest_integrated_semantics(tx, *, set_key: str, semantic_dict: dict):
    tx.run(
        """
        UNWIND $rows AS row
        MATCH (ic:IntegratedChapter {scope:"INTEGRATED", set_key:$set_key, chapter_id:row.chapter_id})

        // ✅ 강력키: set_key + chapter_id + issue_id
        MERGE (s:SemanticIssue {
          scope:"INTEGRATED",
          set_key:$set_key,
          id: row.sid
        })
        SET s.issue_id    = row.issue_id,
            s.title       = row.title,
            s.chapter_id  = row.chapter_id,
            s.summary     = row.summary

        MERGE (ic)-[:HAS_INTEGRATED_SEMANTIC]->(s)
        """,
        set_key=set_key,
        rows=[
            {
                "chapter_id": cid,
                "issue_id": issue["issue_id"],
                "title": issue["issue_title"],
                "summary": issue.get("issue_summary"),
                "sid": f"{set_key}::{cid}::{issue['issue_id']}",  # ✅ 핵심
            }
            for cid, ch in semantic_dict.items()
            for issue in ch.get("issues", [])
        ],
    )


# =========================================================
# 4) Integrated Reasoning ingest
#    - ReasoningIssue 키를 issue_title 그대로로 두면,
#      타이틀 미세 변경/공백/표기차이로 중복 생길 수 있음.
#      => id는 stable hash로 고정.
# =========================================================
"""
IntegratedSnapshot
└─ IntegratedChapter
    └─ HAS_INTEGRATED_REASONING
         └─ ReasoningIssue
              └─ HAS_STEP
                   └─ ReasoningStep (scope=INTEGRATED)
                        └─ based_on_raw (JSON)

"""
def ingest_integrated_reasoning(tx, *, set_key: str, reasoning_dict: dict):
    
    rows = []
    for cid, ch in reasoning_dict.items():
        for issue in ch.get("reasoning", []):
            title = issue["issue_title"]
            rid = stable_reasoning_issue_id(cid, title)
            rows.append(
                {
                    "chapter_id": cid,
                    "rid": rid,
                    "issue_title": title,
                    "summary": issue.get("summary"),
                }
            )

    tx.run(
        """
        UNWIND $rows AS row
        MATCH (ic:IntegratedChapter {scope:"INTEGRATED", set_key:$set_key, chapter_id:row.chapter_id})
        MERGE (r:ReasoningIssue {scope:"INTEGRATED", set_key:$set_key, id:row.rid})
        SET r.chapter_id  = row.chapter_id,
            r.issue_title = row.issue_title,
            r.summary     = row.summary
        MERGE (ic)-[:HAS_INTEGRATED_REASONING]->(r)
        """,
        set_key=set_key,
        rows=rows,
    )
# =========================================================
# 4-1) Integrated ReasoningStep ingest
#      - Integrated ReasoningIssue -> HAS_STEP -> ReasoningStep
# =========================================================

def ingest_integrated_reasoning_steps(driver, *, set_key: str, reasoning_dict: dict):
    """
    reasoning_dict = integrated["reasoning"]
    (03_reasoning_dict.json 구조)
    """

    with driver.session() as session:
        for chapter_id, ch in reasoning_dict.items():
            for issue_idx, issue in enumerate(ch.get("reasoning", [])):
                issue_title = issue["issue_title"]
                rid = stable_reasoning_issue_id(chapter_id, issue_title)

                for step in issue.get("steps", []):
                    step_id = step.get("step_id")
                    if not step_id:  # 🔒 보호막
                        continue

                    step_uid = f"{set_key}::{chapter_id}::{rid}::{step_id}"

                    session.run(
                        """
                        MATCH (ri:ReasoningIssue {
                          scope:"INTEGRATED",
                          set_key:$set_key,
                          id:$rid
                        })

                        MERGE (rs:ReasoningStep {
                          scope:"INTEGRATED",
                          set_key:$set_key,
                          id:$step_uid
                        })
                        SET rs.chapter_id   = $chapter_id,
                            rs.issue_idx    = $issue_idx,
                            rs.issue_title  = $issue_title,
                            rs.step_id      = $step_id,
                            rs.step_type    = $step_type,
                            rs.description  = $description,
                            rs.based_on_raw = $based_on

                        MERGE (ri)-[:HAS_STEP]->(rs)
                        """,
                        set_key=set_key,
                        rid=rid,
                        step_uid=step_uid,
                        chapter_id=chapter_id,
                        issue_idx=issue_idx,
                        issue_title=issue_title,
                        step_id=step_id,
                        step_type=step.get("step_type"),
                        description=step.get("description"),
                        based_on=step.get("based_on", []) or [],
                    )

    print("✅ Integrated ReasoningStep ingest 완료")

# =========================================================
# 5) Reasoning <-> Semantic alignment ingest
#    - reasoning_enriched.json이 issue_title + semantic_issue_id를 주니까
#      ReasoningIssue는 동일한 stable_id를 여기서도 계산해서 MATCH.
# =========================================================

def ingest_reasoning_alignment(*, set_key: str, json_path: str, driver):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    with driver.session() as session:
        for chapter_id, ch in data.items():
            for issue in ch.get("reasoning", []):
                issue_title = issue["issue_title"]
                semantic_issue_id = issue.get("semantic_issue_id")
                confidence = issue.get("alignment_confidence")

                if not semantic_issue_id:
                    continue

                rid = stable_reasoning_issue_id(chapter_id, issue_title)
                sem_sid = f"{set_key}::{chapter_id}::{issue['semantic_issue_id']}"

                session.run(
                    """
                    MATCH (r:ReasoningIssue {scope:"INTEGRATED", set_key:$set_key, id:$rid})
                    MATCH (s:SemanticIssue  {scope:"INTEGRATED", set_key:$set_key, id:$sem_sid})
                    MERGE (r)-[a:ALIGNED_WITH]->(s)
                    SET a.confidence = $confidence
                    """,
                    set_key=set_key,
                    rid=rid,
                    sem_sid=sem_sid,
                    confidence=confidence,
                )

    print("✅ Neo4j reasoning-semantic alignment ingest 완료")

# =========================================================
# Full ingest entry
# =========================================================
"""
IntegratedSnapshot
└─ IntegratedChapter
   ├─ HAS_INTEGRATED_REASONING
   │  └─ ReasoningIssue
   │     └─ HAS_STEP
   │        └─ ReasoningStep
   │           └─ BASED_ON → Article / LawTarget
   └─ HAS_INTEGRATED_SEMANTIC

"""

def run_full_integrated_ingest(
    driver,
    ctx: IntegratedIngestContext,
    *,
    snapshot: dict,
):
    # set_key 확보
    set_key = (
        ctx.set_key
        if hasattr(ctx, "set_key") and ctx.set_key
        else infer_set_key_from_reasoning_path(ctx.reasoning_enriched_path)
    )

    print(f"🚀 Start Integrated Ingest [{ctx.prefix}]")
    print(f"🔑 set_key = {set_key}")
    
    # --- TX 1: core integrated ingest ---
    with driver.session() as session:
                # 🔽 🔽 🔽 여기서 추출 🔽 🔽 🔽
        valid_from = snapshot["valid_from"]
        valid_to   = snapshot.get("valid_to")

        law_meta = snapshot["law"]
        promulgated_at = law_meta["promulgated_at"]
        effective_at   = law_meta.get("effective_at", promulgated_at)
        
        # 0) Snapshot
        ingest_integrated_snapshot(
            session,
            set_key=set_key,
            promulgated_at=promulgated_at,
            effective_at=effective_at,
            valid_from=valid_from,
            valid_to=valid_to,
        )

        # 1) IntegratedChapter
        ingest_integrated_chapters(
            session,
            set_key=set_key,
            semantic_dict=ctx.semantic_dict,
        )

        # 2) Source Chapter linking
        link_all_integrated_chapters(
            session,
            set_key=set_key,
            semantic_dict=ctx.semantic_dict,
        )

        # 3) Semantic
        ingest_integrated_semantics(
            session,
            set_key=set_key,
            semantic_dict=ctx.semantic_dict,
        )

        # 4) Reasoning
        ingest_integrated_reasoning(
            session,
            set_key=set_key,
            reasoning_dict=ctx.reasoning_dict,
        )

    # --- TX 2: integrated reasoning steps ---
    ingest_integrated_reasoning_steps(
        driver,
        set_key=set_key,
        reasoning_dict=ctx.reasoning_dict,
    )

    # 5) Alignment (파일 IO → tx 밖)
    ingest_reasoning_alignment(
        set_key=set_key,
        json_path=ctx.reasoning_enriched_path,
        driver=driver,
    )

    print(f"✅ Integrated Ingest Completed [{ctx.prefix}]")


"""
✅ 전제: 현재 모델 요약 (확정 기준)

Norm 쪽
Law (scope, id)
└─ HAS_VERSION
   └─ LawVersion (scope, law_id, version_key)
      └─ HAS_CHAPTER
         └─ Chapter (scope, version_key, id)
            └─ HAS_SECTION / HAS_ARTICLE / ...

Integrated 쪽
IntegratedSnapshot (scope:"INTEGRATED", set_key)
└─ HAS_INTEGRATED_CHAPTER
   └─ IntegratedChapter (scope:"INTEGRATED", set_key, chapter_id)
        ├─ DERIVED_FROM → Chapter (LAW, version_key, id)
        ├─ DERIVED_FROM → Chapter (DECREE, version_key, id)
        └─ DERIVED_FROM → Chapter (RULE, version_key, id)
        ├─ HAS_INTEGRATED_SEMANTIC → SemanticIssue
        └─ HAS_INTEGRATED_REASONING → ReasoningIssue
             └─ ALIGNED_WITH → SemanticIssue

1️⃣ IntegratedSnapshot에 존재하는 모든 set_key 목록
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED"})
RETURN s.set_key
ORDER BY s.set_key;
             
 3️⃣ set_key + 유효기간 같이 보기 (디버그용)
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED"})
RETURN
  s.set_key,
  s.valid_from,
  s.valid_to,
  s.promulgated_at,
  s.effective_at
ORDER BY s.valid_from DESC;

4️⃣ 특정 set_key 하나 골라서 구조 확인
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:"LAW_20201222_17651__DECREE_20210217_31448__RULE_20210316_00840"})
RETURN s;

🧠 정리 (중요한 개념 다시 한 번)
set_key는 DB에 이미 다 들어가 있음
Neo4j Browser에서 $set_key 쓸 때만
👉 params를 같이 안 주면 에러 나는 것
그건 쿼리 문제지, ingest 문제 아님
SaaS/백엔드 코드에서는:
파이프라인 → set_key 자동 생성
ingest → MERGE (IntegratedSnapshot {set_key})
조회 → 코드에서 파라미터 바인딩됨
수동 params는 개발자용 확인 과정일 뿐


4️⃣ Integrated 레이어 최종 점검 (이미 거의 끝)
(1) Integrated → Source Chapter 연결 확인
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic)
      -[:DERIVED_FROM]->(c:Chapter)
RETURN
  ic.chapter_id,
  c.scope        AS source_scope,
  c.version_key,
  c.id           AS chapter_id
ORDER BY ic.chapter_id, source_scope;

✅ 기대
chapter_id마다 LAW / DECREE / RULE 3줄
version_key가 set_key와 일치해야 정상




IntegratedSnapshot (set_key)
└─ IntegratedChapter (chapter_id)
   ├─ SemanticIssue   (chapter_id 고정)
   └─ ReasoningIssue  (chapter_id 고정)



(2) Integrated Semantic이 챕터 단위로 잘 묶였는지
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic)
OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_SEMANTIC]->(sem:SemanticIssue)
WHERE sem.chapter_id = ic.chapter_id
RETURN
  ic.chapter_id,
  count(sem) AS semantic_cnt
ORDER BY ic.chapter_id;

// ❗ 챕터 불일치 SemanticIssue 찾기
MATCH (ic:IntegratedChapter {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_SEMANTIC]->(sem:SemanticIssue)
WHERE sem.chapter_id <> ic.chapter_id
RETURN ic.chapter_id, sem.chapter_id, sem.issue_id;
👉 아무것도 안 나오면 완벽, 나오면 “과거 오염 잔존”



(3) Integrated Reasoning ↔ Semantic 정렬 확인
MATCH (r:ReasoningIssue {scope:"INTEGRATED", set_key:$set_key})
      -[a:ALIGNED_WITH]->(s:SemanticIssue {scope:"INTEGRATED", set_key:$set_key})
WHERE r.chapter_id = s.chapter_id
RETURN
  r.chapter_id,
  r.issue_title,
  s.issue_id,
  a.confidence
ORDER BY r.chapter_id;

// ❗ 챕터가 다른데도 정렬된 경우
MATCH (r:ReasoningIssue {scope:"INTEGRATED", set_key:$set_key})
      -[:ALIGNED_WITH]->(s:SemanticIssue {scope:"INTEGRATED", set_key:$set_key})
WHERE r.chapter_id <> s.chapter_id
RETURN
  r.chapter_id AS reasoning_chapter,
  r.issue_title,
  s.chapter_id AS semantic_chapter,
  s.issue_id;
👉 아무것도 안 나오면 완벽, 나오면 “과거 오염 잔존”

  
🧱 1️⃣ Norm ingest 구조 검증 (버전 기준)
(1) Law → Chapter → Article 구조
MATCH (l:Law)-[:HAS_VERSION]->(v:LawVersion)
      -[:HAS_CHAPTER]->(c:Chapter)
      -[:HAS_ARTICLE]->(a:Article)
RETURN
  l.scope,
  l.id        AS law_id,
  v.version_key,
  c.id        AS chapter_id,
  count(a)   AS article_cnt
ORDER BY l.scope, v.version_key, chapter_id;

기대 결과
LAW / DECREE / RULE 각각 나옴
article_cnt > 0
scope 섞여 있으면 실패


(2) NormUnit이 Article에 제대로 붙었는지
MATCH (n:NormUnit)-[:NORM_UNIT_OF]->(a:Article)
RETURN
  n.scope,
  n.version_key,
  count(n) AS norm_cnt
ORDER BY n.scope, n.version_key;

기대결과
LAW / DECREE / RULE 각각 존재
통합(INTEGRATED) 없어야 정상



(3) CrossRef 정상 여부 (internal / external 포함)
MATCH (n:NormUnit)-[r:REFERS_TO]->(t:LawTarget)
RETURN
  n.scope,
  n.version_key,
  r.type,
  count(*) AS cnt
ORDER BY n.scope, n.version_key, r.type;


2️⃣ 령 / 규칙 전용 추가 요소 확인
(4) 제·개정 이유 (RevisionReason)
MATCH (l:Law {scope:"DECREE"})-[:HAS_VERSION]->(v)
      -[:HAS_REVISION_REASON]->(r)
RETURN l.id, v.version_key, count(r);

MATCH (l:Law {scope:"RULE"})-[:HAS_VERSION]->(v)
      -[:HAS_REVISION_REASON]->(r)
RETURN l.id, v.version_key, count(r);

count > 0
LAW에는 없어도 정상

(5) 개정문 (Amendment)
MATCH (l:Law)-[:HAS_VERSION]->(v)
      -[:HAS_AMENDMENT]->(a)
RETURN l.scope, v.version_key, count(a)
ORDER BY l.scope, v.version_key;

(6) 별표 (Annex)
MATCH (l:Law)-[:HAS_VERSION]->(v)
      -[:HAS_ANNEX]->(a:Annex)
RETURN l.scope, v.version_key, count(a)
ORDER BY l.scope, v.version_key;


3️⃣ Logic ingest (Semantic / Reasoning) — 법/령/규칙 쪽
(7) Chapter → SemanticIssue
MATCH (v:LawVersion)-[:HAS_CHAPTER]->(c:Chapter)
      -[:HAS_SEMANTIC_ISSUE]->(s:SemanticIssue)
RETURN c.scope, c.version_key, count(s)
ORDER BY c.scope, c.version_key;


(8) Chapter → ReasoningIssue → Step
MATCH (v:LawVersion)-[:HAS_CHAPTER]->(c:Chapter)
      -[:HAS_REASONING_ISSUE]->(r)
      -[:HAS_STEP]->(st)
RETURN c.scope, c.version_key, count(r), count(st)
ORDER BY c.scope, c.version_key;


(A) ch2장 Article 노드 직접 시각화
MATCH (s:IntegratedSnapshot {set_key:$set_key})
-[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
-[:DERIVED_FROM]->(c:Chapter)

OPTIONAL MATCH (c)-[:HAS_ARTICLE]->(a1:Article)
OPTIONAL MATCH (c)-[:HAS_SECTION]->(sec)
OPTIONAL MATCH (sec)-[:HAS_ARTICLE]->(a2:Article)
OPTIONAL MATCH (sec)-[:HAS_SUBDIVISION]->(sd)
OPTIONAL MATCH (sd)-[:HAS_ARTICLE]->(a3:Article)

RETURN ic, c, sec, sd, a1, a2, a3;


👁️ 시각화 쿼리 (Integrated 중심)
1)6장 전체 “전체 사고 맵”으로 보기 (풀버전)
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
OPTIONAL MATCH (ic)-[:DERIVED_FROM]->(c:Chapter)
OPTIONAL MATCH (c)-[:HAS_ARTICLE]->(a:Article)
OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_SEMANTIC]->(sem:SemanticIssue)
OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_REASONING]->(r:ReasoningIssue)
OPTIONAL MATCH (r)-[:ALIGNED_WITH]->(sem)
RETURN ic, c, a, sem, r;

2) Reasoning → Semantic “사고 연결” 시각화 (핵심)
MATCH (snap:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
      -[:HAS_INTEGRATED_REASONING]->(r)
      -[:ALIGNED_WITH]->(sem:SemanticIssue)
WHERE sem.chapter_id = ic.chapter_id
RETURN ic, r, sem;

# 오염탐지 확인용
MATCH (snap:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
      -[:HAS_INTEGRATED_REASONING]->(r)
      -[:ALIGNED_WITH]->(sem:SemanticIssue)
WHERE sem.chapter_id <> ic.chapter_id
RETURN ic, r, sem;
👉 아무것도 안 나오면 완벽, 나오면 “과거 오염 잔존”


3) 2장의 SemanticIssue를 눈으로 보기
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
      -[:HAS_INTEGRATED_SEMANTIC]->(sem:SemanticIssue)
WHERE sem.chapter_id = ic.chapter_id
RETURN ic, sem;


4)또는 법/령/규칙 각각 보고 싶으면:
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
MATCH (ic)-[:DERIVED_FROM]->(c:Chapter)
OPTIONAL MATCH (c)-[r:HAS_SECTION|HAS_ARTICLE]->(n)
RETURN ic, c, r, n;

========================================================
===============================================================
<수정해서 가야하는 방향>
IntegratedSnapshot (2017-12-19)
└─ HAS_INTEGRATED_CHAPTER → IntegratedChapter (CH_6)
    ├─ DERIVED_FROM → Chapter (LAW, version_key=20171219_15221)
    ├─ DERIVED_FROM → Chapter (DECREE, version_key=…)
    └─ DERIVED_FROM → Chapter (RULE, version_key=…)
👉 Integrated는 “Law의 통합”이 아니라
👉 “Version 조합의 통합”이다.

Law를 불변으로 두면 가능한 것
Law = 정체성
LawVersion = 시간
IntegratedSnapshot = 시점 조합
IntegratedSemantic / Reasoning = 의미 해석 레이어
이건 시간·의미·정체성을 분리한 정석 구조야.
👉 판례는 공포일 + 공포번호를 기준으로 말한다.

IntegratedSnapshot 스키마
“2017-12-19 기준으로 유효한 시행령/시행규칙 찾기” 로직
판례 citation → snapshot_key 매핑 함수
reasoning → article 조회 시 version_key 강제

"""