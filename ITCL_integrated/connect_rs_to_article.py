# ITCL_integrated/connect_rs_to_article.py

"""
역할: Integrated ReasoningStep의 based_on_raw(=JSON의 step["based_on"])를
      Neo4j의 Article 또는 IntegratedLawTarget으로 연결한다.

전제:
- Integrated ingest(ingest.py)에서 이미 아래가 만들어져 있어야 함.
  ReasoningIssue(scope=INTEGRATED,set_key,id=rid)
    -[:HAS_STEP]->
  ReasoningStep(scope=INTEGRATED,set_key,id=step_uid, based_on_raw=[...])

이 파일은 절대 Step/Issue를 만들지 않는다.
오직:
  (ReasoningStep)-[:BASED_ON]->(Article | IntegratedLawTarget)
만 수행한다.

(IntegratedChapter)
 └─ DERIVED_FROM {source_scope}
     └─ (Chapter {scope, version_key, id})

(LawVersion)
 └─ HAS_CHAPTER
     └─ (Chapter {scope, version_key, id})
         └─ HAS_ARTICLE
             └─ (Article {scope, version_key, id})

"""

import os
import re
import json
import hashlib
import dotenv
import neo4j

dotenv.load_dotenv()


# =========================================================
# 0) set_key helpers
# =========================================================

def parse_set_key(set_key: str) -> tuple[str, str, str]:
    """
    set_key 예:
    LAW_20171219_15221__DECREE_20171219_15222__RULE_20171219_15223
    return: (law_vkey, decree_vkey, rule_vkey)
    """
    if not set_key or not isinstance(set_key, str):
        raise ValueError(f"Invalid set_key: {set_key}")

    parts = set_key.split("__")
    kv = {}
    for p in parts:
        if "_" not in p:
            continue
        head, rest = p.split("_", 1)
        kv[head] = rest

    law_vkey = kv.get("LAW")
    decree_vkey = kv.get("DECREE")
    rule_vkey = kv.get("RULE")

    if not (law_vkey and decree_vkey and rule_vkey):
        raise ValueError(f"Cannot parse set_key => {set_key}")

    return law_vkey, decree_vkey, rule_vkey


def version_key_from_set_key(set_key: str, scope: str) -> str:
    law_vkey, decree_vkey, rule_vkey = parse_set_key(set_key)
    scope = (scope or "").upper()

    if scope == "LAW":
        return law_vkey
    if scope == "DECREE":
        return decree_vkey
    if scope == "RULE":
        return rule_vkey

    raise ValueError(f"Unknown scope for version_key: {scope}")


# =========================================================
# 1) stable ids (ReasoningIssue id)  <-- ingest.py와 동일해야 함
# =========================================================

def stable_reasoning_issue_id(chapter_id: str, issue_title: str) -> str:
    """
    ingest.py에서 ReasoningIssue id 생성 규칙과 반드시 같아야 함.
    """
    base = (issue_title or "").strip()
    # 공백/개행 흔들림 최소화(선택이지만 안전)
    base = re.sub(r"\s+", " ", base)
    h = hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]
    return f"{chapter_id}_REASON_{h}"


# =========================================================
# 2) citation parsing
# =========================================================

def parse_citation(citation: str):
    """
    예)
    - 국제조세조정에 관한 법률 제65조
    - 국제조세조정에 관한 법률 제34조의2
    """
    if not citation or not isinstance(citation, str):
        return None

    citation = citation.strip()

    pattern = r"(.+?)\s+제(\d+)조(?:의(\d+))?"
    m = re.match(pattern, citation)
    if not m:
        return None

    law_name = m.group(1).strip()
    main = m.group(2)
    sub = m.group(3)

    article_no = f"{main}_{sub}" if sub else main
    article_id = f"ART_{article_no}"

    return {
        "law_name": law_name,
        "article_no": article_no,
        "article_id": article_id,
        "raw": citation,
    }


def infer_scope_from_law_name(law_name: str) -> str:
    if not law_name:
        return "LAW"
    if law_name.endswith("시행령"):
        return "DECREE"
    if law_name.endswith("시행규칙"):
        return "RULE"
    return "LAW"


# =========================================================
# 3) DB matching (version_key 필수)
# =========================================================

def article_exists_in_db(
    driver,
    *,
    law_name: str,
    scope: str,
    version_key: str,
    article_id: str,
) -> bool:
    """
    Law(name+scope) + LawVersion(scope+version_key)로 버전 고정 후,
    Chapter 직속 / Section/Subdivision 하위 어디에 있든 Article을 찾는다.
    """
    query = """
    MATCH (l:Law {scope:$scope, name:$law_name})
    MATCH (l)-[:HAS_VERSION]->(v:LawVersion {scope:$scope, version_key:$version_key})
    CALL (v) {
      MATCH (v)-[:HAS_CHAPTER]->(ch:Chapter)
      MATCH (ch)-[:HAS_ARTICLE]->(a:Article {scope:$scope, version_key:$version_key, id:$article_id})
      RETURN a LIMIT 1
      UNION
      MATCH (v)-[:HAS_CHAPTER]->(ch:Chapter)
      MATCH (ch)-[:HAS_SECTION|HAS_SUBDIVISION*0..]->(x)
      MATCH (x)-[:HAS_ARTICLE]->(a:Article {scope:$scope, version_key:$version_key, id:$article_id})
      RETURN a LIMIT 1
    }
    RETURN a LIMIT 1
    """
    with driver.session() as session:
        rec = session.run(
            query,
            scope=scope,
            law_name=law_name,
            version_key=version_key,
            article_id=article_id,
        ).single()
        return rec is not None


# =========================================================
# 4) Connectors: ReasoningStep -> Article | IntegratedLawTarget
# =========================================================

def connect_rs_to_article(
    driver,
    *,
    set_key: str,
    step_uid: str,
    law_name: str,
    scope: str,
    version_key: str,
    article_id: str,
    raw_citation: str,
):
    """
    ReasoningStep -[:BASED_ON]-> Article 연결
    + 같은 citation으로 붙어있던 IntegratedLawTarget BASED_ON은 제거(있으면)
    """
    query = """
    MATCH (rs:ReasoningStep {scope:"INTEGRATED", set_key:$set_key, id:$step_uid})

    MATCH (l:Law {scope:$scope, name:$law_name})
    MATCH (l)-[:HAS_VERSION]->(v:LawVersion {scope:$scope, version_key:$version_key})

    CALL (v) {
      MATCH (v)-[:HAS_CHAPTER]->(ch:Chapter)
      MATCH (ch)-[:HAS_ARTICLE]->(a:Article {scope:$scope, version_key:$version_key, id:$article_id})
      RETURN a LIMIT 1
      UNION
      MATCH (v)-[:HAS_CHAPTER]->(ch:Chapter)
      MATCH (ch)-[:HAS_SECTION|HAS_SUBDIVISION*0..]->(x)
      MATCH (x)-[:HAS_ARTICLE]->(a:Article {scope:$scope, version_key:$version_key, id:$article_id})
      RETURN a LIMIT 1
    }

    MERGE (rs)-[:BASED_ON]->(a)

    """
    with driver.session() as session:
        session.run(
            query,
            set_key=set_key,
            step_uid=step_uid,
            scope=scope,
            law_name=law_name,
            version_key=version_key,
            article_id=article_id,
            raw_citation=raw_citation,
        )


def connect_rs_to_lawtarget(
    driver,
    *,
    set_key: str,
    step_uid: str,
    citation: str,
    target_scope: str,
):
    """
    Article 매칭 실패시 fallback.
    - 기존 LawTarget(노름 인제스트)와 충돌 방지: IntegratedLawTarget 사용
    - target_scope: "LAW"/"DECREE"/"RULE"/"EXTERNAL" 같은 힌트 저장
    """
    query = """
    MATCH (rs:ReasoningStep {scope:"INTEGRATED", set_key:$set_key, id:$step_uid})
    MERGE (t:IntegratedLawTarget {scope:"INTEGRATED", set_key:$set_key, name:$citation})
    ON CREATE SET
      t.created_at = datetime(),
      t.target_scope = $target_scope
    MERGE (rs)-[:BASED_ON]->(t)
    """
    with driver.session() as session:
        session.run(
            query,
            set_key=set_key,
            step_uid=step_uid,
            citation=citation,
            target_scope=target_scope,
        )


# =========================================================
# 5) Main: JSON 순회 (Step 생성 없음!)
# =========================================================

def ingest_reasoning_steps(  # ✅ 이름 유지(요청 반영). 하지만 "connect-only"로 동작한다.
    driver,
    *,
    reasoning_json: dict,
    set_key: str,
):
    """
    reasoning_json: 05_reasoning_enriched.json 최상위 구조 (CH_1, CH_2 ... dict)
    set_key: Integrated 세트 키
    """
    if not reasoning_json:
        return

    for _, chapter in reasoning_json.items():
        chapter_id = chapter.get("chapter_id") or chapter.get("id")
        if not chapter_id:
            continue

        reasoning_list = chapter.get("reasoning") or []
        for issue_idx, issue in enumerate(reasoning_list):
            issue_title = issue.get("issue_title") or ""
            rid = stable_reasoning_issue_id(chapter_id, issue_title)

            for step in issue.get("steps", []) or []:
                step_id = step.get("step_id")
                if step_id is None:
                    continue

                # ✅ ingest.py에서 만든 step_uid 규칙과 동일해야 한다.
                step_uid = f"{set_key}::{chapter_id}::{rid}::{step_id}"

                for citation in (step.get("based_on", []) or []):
                    parsed = parse_citation(citation)

                    if not parsed:
                        connect_rs_to_lawtarget(
                            driver,
                            set_key=set_key,
                            step_uid=step_uid,
                            citation=citation,
                            target_scope="EXTERNAL",
                        )
                        continue

                    scope = infer_scope_from_law_name(parsed["law_name"])

                    try:
                        vkey = version_key_from_set_key(set_key, scope)
                    except Exception:
                        connect_rs_to_lawtarget(
                            driver,
                            set_key=set_key,
                            step_uid=step_uid,
                            citation=parsed["raw"],
                            target_scope="EXTERNAL",
                        )
                        continue

                    if article_exists_in_db(
                        driver,
                        law_name=parsed["law_name"],
                        scope=scope,
                        version_key=vkey,
                        article_id=parsed["article_id"],
                    ):
                        connect_rs_to_article(
                            driver,
                            set_key=set_key,
                            step_uid=step_uid,
                            law_name=parsed["law_name"],
                            scope=scope,
                            version_key=vkey,
                            article_id=parsed["article_id"],
                            raw_citation=parsed["raw"],
                        )
                    else:
                        connect_rs_to_lawtarget(
                            driver,
                            set_key=set_key,
                            step_uid=step_uid,
                            citation=parsed["raw"],
                            target_scope=scope,
                        )


# =========================================================
# 6) smoke helper
# =========================================================

if __name__ == "__main__":
    URI = os.getenv("NEO4J_URI", "neo4j+s://3dfa7316.databases.neo4j.io")
    AUTH = ("neo4j", os.getenv("NEO4J_PASSWORD", "password"))
    driver = neo4j.GraphDatabase.driver(URI, auth=AUTH)

    set_key = os.getenv("ITCL_SET_KEY")
    path = os.getenv("ITCL_REASONING_ENRICHED_PATH")

    if not set_key or not path:
        raise ValueError("Need ITCL_SET_KEY and ITCL_REASONING_ENRICHED_PATH env vars")

    with open(path, "r", encoding="utf-8") as f:
        reasoning_json = json.load(f)

    ingest_reasoning_steps(driver, reasoning_json=reasoning_json, set_key=set_key)
    print("🔥 connect_rs_to_article done")


"""
1️⃣ ReasoningStep + 연결된 조문 (가장 중요)
MATCH (rs:ReasoningStep {scope:"INTEGRATED"})-[:BASED_ON]->(a:Article)
RETURN
  rs.chapter_id   AS chapter,
  rs.issue_idx    AS issue_idx,
  rs.issue_title  AS issue_title,
  rs.step_id      AS step_id,
  rs.step_type    AS step_type,
  rs.description  AS reasoning_step,
  a.id            AS article_id,
  a.article_no    AS article_no,
  a.title         AS article_title
ORDER BY chapter, issue_idx, step_id;

🔍 ReasoningStep 노드 자체 중복 확인 (정석)
MATCH (rs:ReasoningStep {scope:"INTEGRATED"})
WITH rs.id AS rid, COUNT(*) AS cnt
WHERE cnt > 1
RETURN rid, cnt;

2️⃣ 특정 챕터 하나만 보기 (예: CH_5)
MATCH (rs:ReasoningStep {scope:"INTEGRATED", chapter_id:"CH_5"})
      -[:BASED_ON]->(a:Article)
RETURN
  rs.issue_title,
  rs.step_id,
  rs.step_type,
  rs.description,
  a.article_no,
  a.title
ORDER BY rs.issue_idx, rs.step_id;

3️⃣ 특정 조문이 어디서 쓰였는지 (역방향)
MATCH (a:Article {id:"ART_65"})<-[:BASED_ON]-(rs:ReasoningStep {scope:"INTEGRATED"})
RETURN
  rs.chapter_id,
  rs.issue_title,
  rs.step_id,
  rs.description
ORDER BY rs.chapter_id, rs.issue_idx;

4️⃣ 아직 Article로 못 간 citation (청소 대상)
MATCH (rs:ReasoningStep {scope:"INTEGRATED"})-[:BASED_ON]->(t:IntegratedLawTarget)
RETURN
  rs.chapter_id,
  rs.issue_title,
  rs.step_id,
  t.target_scope,
  t.name
ORDER BY rs.chapter_id;

5️⃣ 시각화용 (Browser 그래프)
MATCH (rs:ReasoningStep {scope:"INTEGRATED"})-[:BASED_ON]->(x)
RETURN rs, x
LIMIT 50;

🔷 Integrated 구조 기반 쿼리들
6️⃣ IntegratedChapter ↔ ReasoningIssue ↔ ReasoningStep ↔ Article (풀 맵)

MATCH (ic:IntegratedChapter {scope:"INTEGRATED", chapter_id:"CH_2"})
OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_REASONING]->(ri:ReasoningIssue)
OPTIONAL MATCH (ri)-[:HAS_STEP]->(rs:ReasoningStep)
OPTIONAL MATCH (rs)-[:BASED_ON]->(a)
OPTIONAL MATCH (ic)-[:DERIVED_FROM]->(c:Chapter)
RETURN ic, ri, rs, a, c;

MATCH (ic:IntegratedChapter {scope:"INTEGRATED", chapter_id:"CH_2"})
OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_REASONING]->(ri:ReasoningIssue)
OPTIONAL MATCH (ri)-[:HAS_STEP]->(rs:ReasoningStep)
OPTIONAL MATCH (rs)-[:BASED_ON]->(a:Article)
OPTIONAL MATCH (a)<-[:HAS_ARTICLE]-(src)
OPTIONAL MATCH (src)<-[:HAS_CHAPTER|HAS_SECTION|HAS_SUBDIVISION*0..]-(c:Chapter)
RETURN ic, ri, rs, a, c;


7️⃣ 시멘틱까지 같이 보기 (구조 검증)
MATCH (ic:IntegratedChapter {scope:"INTEGRATED", chapter_id:"CH_2"})
OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_SEMANTIC]->(s:SemanticIssue)
OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_REASONING]->(ri:ReasoningIssue)
OPTIONAL MATCH (ri)-[:HAS_STEP]->(rs:ReasoningStep)
OPTIONAL MATCH (rs)-[:BASED_ON]->(a)
RETURN ic, s, ri, rs, a;


8️⃣ 사람이 읽기 좋은 테이블 (최종 뷰)
MATCH (ic:IntegratedChapter {scope:"INTEGRATED", chapter_id:"CH_2"})
MATCH (ic)-[:HAS_INTEGRATED_REASONING]->(ri)
MATCH (ri)-[:HAS_STEP]->(rs)
MATCH (rs)-[:BASED_ON]->(a:Article)
RETURN
  ic.chapter_id    AS chapter,
  ri.issue_title   AS issue,
  rs.step_id       AS step,
  rs.step_type     AS step_type,
  rs.description   AS reasoning,
  a.article_no     AS article,
  a.title          AS article_title
ORDER BY ri.issue_title, rs.step_id;

9️⃣ 특정 조문이 Integrated 어디서 쓰였는지 (LAW/DECREE/RULE 통합)

MATCH (l:Law)
WHERE l.name IN [
  "국제조세조정에 관한 법률",
  "국제조세조정에 관한 법률 시행령",
  "국제조세조정에 관한 법률 시행규칙"
]
MATCH (l)-[:HAS_VERSION]->(:LawVersion)
      -[:HAS_CHAPTER]->(:Chapter)
      -[:HAS_SECTION|HAS_SUBDIVISION|HAS_ARTICLE*0..]->(a:Article)
WHERE a.id STARTS WITH "ART_65"
MATCH (a)<-[:BASED_ON]-(rs:ReasoningStep {scope:"INTEGRATED"})
MATCH (ri:ReasoningIssue)-[:HAS_STEP]->(rs)
MATCH (ic:IntegratedChapter)-[:HAS_INTEGRATED_REASONING]->(ri)
RETURN
  l.source_type AS scope,
  l.name        AS law_name,
  a.id,
  ic.chapter_id,
  ri.issue_title,
  rs.step_id,
  rs.description
ORDER BY scope, a.id, toInteger(rs.step_id);

✅ 안전한 디버그 버전 (권장)
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED"})
RETURN
  s.set_key,
  s.valid_from,
  s.valid_to,
  s.promulgated_at,
  s.effective_at
ORDER BY s.valid_from;
✅ date / datetime 혼용 대응 버전
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED"})
WHERE date(s.valid_from) <= date("2017-12-19")
  AND (s.valid_to IS NULL OR date(s.valid_to) > date("2017-12-19"))
RETURN s;

"""