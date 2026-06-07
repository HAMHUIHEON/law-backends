# ITCL_integrated/connect_rs_to_article.py

"""
JSON 로드
 └─ (CH_x 딕셔너리) chapter 순회
     └─ reasoning(issue) 순회
         └─ steps 순회
             └─ based_on 순회
                 ├─ parse_citation
                 ├─ infer_scope
                 ├─ article_exists_in_db ?
                 │    ├─ YES → ReasoningStep → Article (AND 기존 LawTarget 엣지 제거)
                 │    └─ NO  → ReasoningStep → LawTarget

IntegratedChapter
 └─ ReasoningIssue
     └─ ReasoningStep
         └─ BASED_ON → Article / LawTarget

         
LAW/DECREE/RULE pipeline
  └─ chapter_semantic
  └─ chapter_reasoning
      ↓
Integrated LLM
  ├─ 02_semantic_dict.json
  ├─ 03_reasoning_dict.json
  ├─ 04_chapter_sr_align.json
  └─ 05_reasoning_enriched.json   ← ★ 여기까지가 LLM
      ↓
connect_rs_to_article.py          ← ★ 지금 파일
      ↓
Neo4j 그래프 완성
         
"""

import re, hashlib
from neo4j import GraphDatabase
import os,json
import dotenv
import neo4j

dotenv.load_dotenv()

#.\neo4j.bat console
URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
AUTH = ("neo4j", os.getenv("NEO4J_PASSWORD","password"))

driver = neo4j.GraphDatabase.driver(URI, auth=AUTH)


def parse_citation(citation: str):
    """
    예)
    - "국제조세조정에 관한 법률 제65조" -> law_name=..., article_no="65"
    - "국제조세조정에 관한 법률 시행령 제113조의2" -> article_no="113_2"
    """
    if not citation or not isinstance(citation, str):
        return None

    citation = citation.strip()

    # "법령명 제113조의2" / "법령명 제113조" 모두 처리
    # 끝의 "조"까지 포함해서 잡음 (불완전 매치 방지)
    pattern = r"(.+?)\s+제(\d+)(?:조의(\d+))?조"
    m = re.match(pattern, citation)
    if not m:
        return None

    law_name = m.group(1).strip()
    main = m.group(2)
    sub = m.group(3)

    article_no = f"{main}_{sub}" if sub else main
    article_id = f"ART_{article_no}"  # DB의 Article.id 규칙과 맞춤

    return {
        "law_name": law_name,
        "article_no": article_no,
        "article_id": article_id,
        "raw": citation,
    }


def infer_scope_from_law_name(law_name: str) -> str:
    # 네 데이터 기준 suffix 규칙
    if law_name.endswith("시행령"):
        return "DECREE"
    if law_name.endswith("시행규칙"):
        return "RULE"
    return "LAW"


def article_exists_in_db(driver, 
                         law_name: str, scope: str, 
                         article_id: str) -> bool:
    """
    핵심:
    - Article은 (scope, id) 기반
    - Chapter/Section/Subdivision 어디에 있든 HAS_ARTICLE로 연결됨
    """
    query = """
    MATCH (l:Law)
    WHERE l.name = $law_name AND (l.scope = $scope OR l.source_type = $scope)
    MATCH (l)-[:HAS_CHAPTER]->(ch:Chapter)
    MATCH (ch)-[:HAS_SECTION|HAS_SUBDIVISION*0..]->(container)
    MATCH (container)-[:HAS_ARTICLE]->(a:Article {scope: $scope, id: $article_id})
    RETURN a
    LIMIT 1
    """
    with driver.session() as session:
        rec = session.run(
            query,
            law_name=law_name,
            scope=scope,
            article_id=article_id,
        ).single()
        return rec is not None


def upsert_reasoning_step(driver, step_uid: str, chapter_id: str, issue_idx: int, issue_title: str, step: dict):
    query = """
    MERGE (rs:ReasoningStep {step_uid: $step_uid})
    SET rs.chapter_id = $chapter_id,
        rs.issue_idx = $issue_idx,
        rs.issue_title = $issue_title,
        rs.step_id = $step_id,
        rs.step_type = $step_type,
        rs.description = $description
    """
    with driver.session() as session:
        session.run(
            query,
            step_uid=step_uid,
            chapter_id=chapter_id,
            issue_idx=issue_idx,
            issue_title=issue_title,
            step_id=step.get("step_id"),
            step_type=step.get("step_type"),
            description=step.get("description"),
        )


def connect_rs_to_article(driver, step_uid: str, law_name: str, scope: str, article_id: str, raw_citation: str):
    """
    - ReasoningStep -> Article 연결
    - (중요) 같은 citation으로 기존 LawTarget에 붙인 BASED_ON이 있으면 제거해서 중복 방지
    """
    query = """
    MATCH (rs:ReasoningStep {step_uid: $step_uid})

    MATCH (l:Law)
    WHERE l.name = $law_name AND (l.scope = $scope OR l.source_type = $scope)

    MATCH (l)-[:HAS_CHAPTER]->(ch:Chapter)
    MATCH (ch)-[:HAS_SECTION|HAS_SUBDIVISION*0..]->(container)
    MATCH (container)-[:HAS_ARTICLE]->(a:Article {scope: $scope, id: $article_id})

    MERGE (rs)-[:BASED_ON]->(a)

    // ✅ 기존 LawTarget 기반 엣지 제거(있으면)
    WITH rs
    OPTIONAL MATCH (rs)-[r:BASED_ON]->(t:LawTarget {name: $raw_citation})
    DELETE r
    """
    with driver.session() as session:
        session.run(
            query,
            step_uid=step_uid,
            law_name=law_name,
            scope=scope,
            article_id=article_id,
            raw_citation=raw_citation,
        )


def connect_rs_to_lawtarget(driver, step_uid: str, citation: str, scope_for_target: str):
    """
    LawTarget은 (scope, name) 유니크 제약이 있을 수 있어서 scope 포함.
    - INTERNAL이라도 DB에 없으면 LawTarget으로 떨어지게 하되 scope는 유지
    - EXTERNAL은 scope="EXTERNAL" 추천
    """
    query = """
    MATCH (rs:ReasoningStep {step_uid: $step_uid})
    MERGE (t:LawTarget {scope: $t_scope, name: $citation})
    ON CREATE SET t.created_at = datetime()
    MERGE (rs)-[:BASED_ON]->(t)
    """
    with driver.session() as session:
        session.run(
            query,
            step_uid=step_uid,
            citation=citation,
            t_scope=scope_for_target,
        )


def ingest_reasoning_steps(driver, reasoning_json: dict):
    """
    reasoning_json: 05_reasoning_enriched.json의 최상위 구조 (CH_1, CH_2 ... 딕셔너리)
    """
    for _, chapter in reasoning_json.items():
        chapter_id = chapter.get("chapter_id")
        reasoning_list = chapter.get("reasoning") or []

        for issue_idx, issue in enumerate(reasoning_list):
            issue_title = issue.get("issue_title")
            steps = issue.get("steps") or []

            for step in steps:
                step_uid = f"{chapter_id}::{issue_idx}::{step.get('step_id')}"

                # 1) step upsert
                upsert_reasoning_step(driver, step_uid, chapter_id, issue_idx, issue_title, step)

                # 2) based_on 연결
                for citation in step.get("based_on", []) or []:
                    parsed = parse_citation(citation)

                    if not parsed:
                        # 파싱 실패는 그냥 EXTERNAL 취급
                        connect_rs_to_lawtarget(driver, step_uid, citation, scope_for_target="EXTERNAL")
                        continue

                    scope = infer_scope_from_law_name(parsed["law_name"])

                    if article_exists_in_db(
                        driver,
                        law_name=parsed["law_name"],
                        scope=scope,
                        article_id=parsed["article_id"],
                    ):
                        connect_rs_to_article(
                            driver,
                            step_uid=step_uid,
                            law_name=parsed["law_name"],
                            scope=scope,
                            article_id=parsed["article_id"],
                            raw_citation=parsed["raw"],
                        )
                    else:
                        # 내부처럼 보이지만 현재 DB에 없으면 LawTarget로
                        # scope는 유지하면 나중에 external/internal 정리가 쉬움
                        connect_rs_to_lawtarget(driver, step_uid, citation, scope_for_target=scope)


"""쿼리
1️⃣ ReasoningStep + 설명 + 연결된 조문 한 번에 보기 (가장 중요)

MATCH (rs:ReasoningStep)-[:BASED_ON]->(a:Article)
RETURN
  rs.chapter_id       AS chapter,
  rs.issue_idx        AS issue_idx,
  rs.issue_title      AS issue_title,
  rs.step_id          AS step_id,
  rs.step_type        AS step_type,
  rs.description      AS reasoning_step,
  a.id                AS article_id,
  a.article_no        AS article_no,
  a.title             AS article_title
ORDER BY chapter, issue_idx, step_id;

2️⃣ 특정 챕터 하나만 집중해서 보기 (예: CH_5)
MATCH (rs:ReasoningStep {chapter_id: "CH_5"})-[:BASED_ON]->(a:Article)
RETURN
  rs.issue_title,
  rs.step_id,
  rs.step_type,
  rs.description,
  a.article_no,
  a.title
ORDER BY rs.issue_idx, rs.step_id;

👉 이건 **“한 장을 법률 해설서처럼 읽는 뷰”**야.
이미 너 이걸 만들려고 이 프로젝트 시작했잖아. 지금 그 상태임.

3️⃣ 한 조문이 어디서 쓰였는지 (역방향 영향도 분석)

예: 국제조세조정법 제65조가 어디서 쓰였나
MATCH (a:Article {article_no: "65"})<-[:BASED_ON]-(rs:ReasoningStep)
RETURN
  rs.chapter_id,
  rs.issue_title,
  rs.step_id,
  rs.description
ORDER BY rs.chapter_id, rs.issue_idx;

👉 이게 나중에 판례 붙이면 **“판사가 왜 이 조문을 썼는지”**로 바로 이어진다.

4️⃣ 아직 Article로 못 간 LawTarget 8개 확인 (청소 대상)

MATCH (rs:ReasoningStep)-[:BASED_ON]->(t:LawTarget)
RETURN
  rs.chapter_id,
  rs.issue_title,
  rs.step_id,
  t.scope,
  t.name
ORDER BY rs.chapter_id;

👉 여기 나온 8개는:
진짜 외부법 (법인세법 등 아직 미적재)
또는 citation 표현이 살짝 어긋난 놈
이건 **“다음 스프린트 백로그”**지, 오류 아님.

5️⃣ 시각화용 (Neo4j Browser에서 그림으로 보기)
MATCH (rs:ReasoningStep)-[:BASED_ON]->(a)
RETURN rs, a
LIMIT 50;

---

IntegratedChapter
 ├─ HAS_REASONING → ReasoningIssue   (⭕ 있음)
 ├─ HAS_SEMANTIC  → SemanticIssue    (⭕ 있음)

ReasoningStep
 └─ BASED_ON → Article / LawTarget   (⭕ 있음)

❌ ReasoningIssue ↔ ReasoningStep 연결 없음


1️⃣ IntegratedChapter ↔ ReasoningIssue ↔ ReasoningStep ↔ Article (풀 연결 시각화)

MATCH (ic:IntegratedChapter {chapter_id: "CH_6"})
OPTIONAL MATCH (ic)-[:HAS_REASONING]->(ri:ReasoningIssue)
OPTIONAL MATCH (ri)-[:HAS_STEP]->(rs:ReasoningStep)
OPTIONAL MATCH (rs)-[:BASED_ON]->(a:Article)
OPTIONAL MATCH (ic)-[:DERIVED_FROM]->(c:Chapter)
RETURN ic, ri, rs, a, c;

👉 Neo4j Browser에서 보면:
중심: IntegratedChapter
가지 1: ReasoningIssue → ReasoningStep → Article
가지 2: DERIVED_FROM → Law Chapter

2️⃣ 시멘틱까지 같이 보고 싶을 때 (겹쳐도 상관없을 때)
MATCH (ic:IntegratedChapter {chapter_id: "CH_6"})
OPTIONAL MATCH (ic)-[:HAS_SEMANTIC]->(s:SemanticIssue)
OPTIONAL MATCH (ic)-[:HAS_REASONING]->(r:ReasoningIssue)
OPTIONAL MATCH (r)-[:HAS_STEP]->(rs:ReasoningStep)
OPTIONAL MATCH (rs)-[:BASED_ON]->(a:Article)
RETURN ic, s, r, rs, a;
👉 이건 구조 검증용이다.
“시멘틱에서 말한 큰 틀 → 리즈닝에서 실제로 쓴 근거”가 어긋나는지 한 번에 보인다.

3️⃣ 사람 눈으로 읽기 좋은 테이블 뷰 (가장 많이 쓰게 될 것)
MATCH (ic:IntegratedChapter {chapter_id: "CH_6"})
MATCH (ic)-[:HAS_REASONING]->(ri)
MATCH (ri)-[:HAS_STEP]->(rs)
MATCH (rs)-[:BASED_ON]->(a:Article)
RETURN
  ic.chapter_id        AS chapter,
  ri.issue_title       AS issue,
  rs.step_id           AS step,
  rs.step_type         AS step_type,
  rs.description       AS reasoning,
  a.article_no         AS article,
  a.title              AS article_title
ORDER BY ri.issue_title, rs.step_id;
👉 이건 나중에:
리포트
QA
“이 엔진이 왜 이런 답을 냈냐” 설명할 때
그대로 써먹는다.

4️⃣ 역방향: 특정 조문이 IntegratedChapter 어디서 쓰였는지
판례 붙이면 가장 강력해지는 쿼리다.

MATCH (l:Law {name:"국제조세조정에 관한 법률", scope:"LAW"}) -> scope에 DECREE, RULE만 바꾸면 됨
MATCH (l)-[:HAS_CHAPTER]->(:Chapter)-[:HAS_SECTION|HAS_SUBDIVISION|HAS_ARTICLE*0..]->(a:Article)
WHERE a.id STARTS WITH "ART_65"
MATCH (a)<-[:BASED_ON]-(rs:ReasoningStep)
MATCH (ri:ReasoningIssue)-[:HAS_STEP]->(rs)
MATCH (ic:IntegratedChapter)-[:HAS_REASONING]->(ri)
RETURN
  l.name AS law_name,
  l.source_type AS scope,
  a.id,
  ic.chapter_id,
  ri.issue_title,
  rs.step_id,
  rs.description
ORDER BY a.id, toInteger(rs.step_id);

"LAW/DECREE/RULE 중 어디에 있든 찾되, 결과에 scope 붙이기”
MATCH (l:Law)
WHERE l.name IN ["국제조세조정에 관한 법률",
                "국제조세조정에 관한 법률 시행령",
                "국제조세조정에 관한 법률 시행규칙"]
MATCH (l)-[:HAS_CHAPTER]->(:Chapter)-[:HAS_SECTION|HAS_SUBDIVISION|HAS_ARTICLE*0..]->(a:Article)
WHERE a.id STARTS WITH "ART_65"
MATCH (a)<-[:BASED_ON]-(rs:ReasoningStep)
MATCH (ri:ReasoningIssue)-[:HAS_STEP]->(rs)
MATCH (ic:IntegratedChapter)-[:HAS_REASONING]->(ri)
RETURN
  l.source_type AS scope,
  l.name AS law_name,
  a.id,
  ic.chapter_id,
  ri.issue_title,
  rs.step_id,
  rs.description
ORDER BY scope, a.id, toInteger(rs.step_id);


👉 “이 조문은 이 장에서 이런 논리로 쓰인다”
사람도 한참 생각해야 나오는 걸, 쿼리 한 방이다.

4️⃣ 앞으로 쿼리 쓸 때 규칙 하나만 지켜
판단 / 필터링 / 의미 구분 → l.scope
원문 추적 / 출처 디버깅 → l.source_type
예시:


"""