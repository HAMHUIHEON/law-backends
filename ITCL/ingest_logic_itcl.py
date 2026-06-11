#ITCL/ingest_logic_itcl.py


from neo4j import GraphDatabase
import os
import dotenv
import neo4j
from ITCL.ingest_norm_itcl import ingest_law, ingest_chapters, ingest_addenda, reset_db
dotenv.load_dotenv()

#.\neo4j.bat console
URI = os.getenv("NEO4J_URI", "neo4j+s://3dfa7316.databases.neo4j.io")
AUTH = ("neo4j", os.getenv("NEO4J_PASSWORD", "password"))

driver = neo4j.GraphDatabase.driver(URI, auth=AUTH)

def ingest_chapter_semantic(tx, scope, vkey, chapter):
    chapter_id = chapter["id"]
    sem_list = chapter.get("chapter_semantic")
    if not sem_list:
        return

    sem = sem_list[0]

    # 1️⃣ Chapter summary (version 기준)
    chapter_summary = sem.get("chapter_summary")
    if chapter_summary:
        tx.run(
            """
            MATCH (c:Chapter {
              scope:$scope,
              version_key:$version_key,
              id:$chapter_id
            })
            SET c.chapter_summary = $chapter_summary
            """,
            scope=scope,
            version_key=vkey,
            chapter_id=chapter_id,
            chapter_summary=chapter_summary,
        )

    # 2️⃣ SemanticIssue
    for issue in sem.get("issues", []):
        sid = f"{chapter_id}_SEM_{issue['issue_id']}"

        tx.run(
            """
            MERGE (s:SemanticIssue {
              scope:$scope,
              version_key:$version_key,
              id:$id
            })
            SET s.issue_id    = $issue_id,
                s.issue_title = $issue_title,
                s.summary     = $summary,
                s.conditions  = $conditions,
                s.effects     = $effects,
                s.exceptions  = $exceptions,
                s.methods     = $methods
            """,
            scope=scope,
            version_key=vkey,
            id=sid,
            issue_id=issue["issue_id"],
            issue_title=issue["issue_title"],
            summary=issue.get("issue_summary"),
            conditions=issue.get("conditions", []),
            effects=issue.get("effects", []),
            exceptions=issue.get("exceptions", []),
            methods=issue.get("methods", []),
        )

        tx.run(
            """
            MATCH (c:Chapter {
              scope:$scope,
              version_key:$version_key,
              id:$chapter_id
            })
            MATCH (s:SemanticIssue {
              scope:$scope,
              version_key:$version_key,
              id:$id
            })
            MERGE (c)-[:HAS_SEMANTIC_ISSUE]->(s)
            """,
            scope=scope,
            version_key=vkey,
            chapter_id=chapter_id,
            id=sid,
        )
        
import hashlib

def stable_issue_id(chapter_id: str, issue_title: str) -> str:
    h = hashlib.sha256(issue_title.encode("utf-8")).hexdigest()[:12]
    return f"{chapter_id}_REASON_{h}"


def ingest_chapter_reasoning(tx, scope, vkey, chapter):
    chapter_id = chapter["id"]
    reasoning_list = chapter.get("chapter_reasoning")
    if not reasoning_list:
        return

    reasoning_obj = reasoning_list[0]

    for issue in reasoning_obj.get("reasoning", []):
        issue_title = issue["issue_title"]

        # ⚠️ 지금은 임시, 추후 stable id로 교체 예정
        rid = stable_issue_id(chapter_id, issue_title)

        tx.run(
            """
            MERGE (r:ReasoningIssue {
              scope:$scope,
              version_key:$version_key,
              id:$id
            })
            SET r.issue_title = $title,
                r.summary     = $summary
            """,
            scope=scope,
            version_key=vkey,
            id=rid,
            title=issue_title,
            summary=issue.get("summary"),
        )

        tx.run(
            """
            MATCH (c:Chapter {
              scope:$scope,
              version_key:$version_key,
              id:$chapter_id
            })
            MATCH (r:ReasoningIssue {
              scope:$scope,
              version_key:$version_key,
              id:$id
            })
            MERGE (c)-[:HAS_REASONING_ISSUE]->(r)
            """,
            scope=scope,
            version_key=vkey,
            chapter_id=chapter_id,
            id=rid,
        )

        for step in issue.get("steps", []):
            sid = f"{rid}_STEP_{step['step_id']}"

            tx.run(
                """
                MERGE (st:ReasoningStep {
                  scope:$scope,
                  version_key:$version_key,
                  id:$id
                })
                SET st.step_id     = $step_id,
                    st.step_type   = $step_type,
                    st.description = $description,
                    st.based_on    = $based_on,
                    st.conditions  = $conditions,
                    st.effects     = $effects,
                    st.exceptions  = $exceptions,
                    st.methods     = $methods
                """,
                scope=scope,
                version_key=vkey,
                id=sid,
                step_id=step["step_id"],
                step_type=step["step_type"],
                description=step["description"],
                based_on=step.get("based_on", []),
                conditions=step.get("conditions", []),
                effects=step.get("effects", []),
                exceptions=step.get("exceptions", []),
                methods=step.get("methods", []),
            )

            tx.run(
                """
                MATCH (r:ReasoningIssue {
                  scope:$scope,
                  version_key:$version_key,
                  id:$rid
                })
                MATCH (st:ReasoningStep {
                  scope:$scope,
                  version_key:$version_key,
                  id:$sid
                })
                MERGE (r)-[:HAS_STEP]->(st)
                """,
                scope=scope,
                version_key=vkey,
                rid=rid,
                sid=sid,
            )


def norm_scope(law_json: dict) -> str:
    st = (law_json.get("source_type") or "").lower()
    if st in ("law",):
        return "LAW"
    if st in ("admrul", "decree"):
        return "DECREE"
    if st in ("admrule", "rule"):
        return "RULE"
    return st.upper() or "UNKNOWN"

def version_key(law: dict) -> str:
    meta = law.get("metadata", {})
    d = meta.get("공포일자")
    n = meta.get("공포번호")
    if not d or not n:
        raise ValueError("공포일자/공포번호 없음 → version_key 생성 불가")
    return f"{d}_{n}"

def run_ingest_logic(law_json):
    scope = norm_scope(law_json)
    vkey  = version_key(law_json)

    with driver.session() as session:
        for ch in law_json["chapters"]:
            session.execute_write(
                ingest_chapter_semantic, scope, vkey, ch
            )
            session.execute_write(
                ingest_chapter_reasoning, scope, vkey, ch
            )
