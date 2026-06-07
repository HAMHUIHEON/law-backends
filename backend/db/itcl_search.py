# db/itcl_search.py
"""
ITCL(국제조세조정에 관한 법률) 통합 레이어 검색 엔진

세 가지 검색 모드:
  1. search_similar_issues   — SemanticIssue 벡터 유사도 검색
  2. get_law_structure       — IntegratedChapter → Article 구조 조회
  3. search_articles_by_topic — ReasoningStep.based_on 역추적으로 관련 조문 탐색
"""

import os
from typing import Optional

import openai
from neo4j import GraphDatabase

EMBED_MODEL = "text-embedding-3-small"


def _embed(text: str, client: openai.OpenAI) -> list[float]:
    return client.embeddings.create(model=EMBED_MODEL, input=[text]).data[0].embedding


class ITCLSearch:

    def __init__(self):
        self._driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
        )
        self._oai = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # ─────────────────────────────────────────────
    # 1. 쟁점 벡터 유사도 검색 (SemanticIssue)
    # ─────────────────────────────────────────────

    def search_similar_issues(self, query: str, top_k: int = 5) -> list[dict]:
        """
        자연어 쿼리와 의미적으로 유사한 ITCL 쟁점을 반환합니다.
        예) "이전가격 정상가격 산정 방법론 분쟁"
        """
        embedding = _embed(query, self._oai)

        with self._driver.session() as session:
            rows = session.run(
                """
                CALL db.index.vector.queryNodes('itcl_issue_embedding', $top_k, $embedding)
                YIELD node AS si, score
                RETURN si.set_key        AS set_key,
                       si.issue_id       AS issue_id,
                       si.title          AS issue_title,
                       si.summary        AS issue_summary,
                       round(score, 4)   AS similarity
                ORDER BY score DESC
                """,
                {"top_k": top_k, "embedding": embedding},
            )
            return [dict(r) for r in rows]

    # ─────────────────────────────────────────────
    # 2. 법령 구조 조회 (최신 스냅샷 → 챕터 → 쟁점)
    # ─────────────────────────────────────────────

    def get_law_structure(self, set_key: Optional[str] = None) -> dict:
        """
        특정(또는 최신) 시행 스냅샷의 챕터별 쟁점 목록을 반환합니다.
        set_key가 없으면 valid_from 기준 최신 스냅샷을 사용합니다.
        """
        with self._driver.session() as session:
            if not set_key:
                r = session.run(
                    """
                    MATCH (s:IntegratedSnapshot {scope:'INTEGRATED'})
                    WHERE s.valid_to IS NULL
                    RETURN s.set_key AS set_key, s.valid_from AS valid_from
                    ORDER BY s.valid_from DESC
                    LIMIT 1
                    """
                ).single()
                if not r:
                    return {}
                set_key = r["set_key"]

            rows = session.run(
                """
                MATCH (s:IntegratedSnapshot {set_key:$set_key})
                      -[:HAS_INTEGRATED_CHAPTER]->(ic:IntegratedChapter)
                OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_SEMANTIC]->(si:SemanticIssue)
                RETURN ic.chapter_id AS chapter_id,
                       ic.name       AS chapter_name,
                       collect({
                         issue_id:    si.issue_id,
                         issue_title: si.title,
                         summary:     si.summary
                       }) AS issues
                ORDER BY ic.chapter_id
                """,
                {"set_key": set_key},
            ).data()

        return {
            "set_key": set_key,
            "chapters": [
                {
                    "chapter_id": r["chapter_id"],
                    "chapter_name": r["chapter_name"],
                    "issues": [
                        i for i in r["issues"]
                        if i.get("issue_id")  # null 필터링
                    ],
                }
                for r in rows
            ],
        }

    # ─────────────────────────────────────────────
    # 3. 조문 역추적 (주제 → 관련 Article)
    # ─────────────────────────────────────────────

    def search_articles_by_topic(
        self, query: str, set_key: Optional[str] = None, top_k: int = 5
    ) -> list[dict]:
        """
        유사 쟁점(SemanticIssue)과 같은 챕터의 ReasoningStep이 BASED_ON으로
        인용한 Article을 역추적합니다.

        경로: SemanticIssue(chapter_id) → ReasoningIssue(chapter_id)
              → ReasoningStep → Article
        """
        issues = self.search_similar_issues(query, top_k=top_k)
        if not issues:
            return []

        sk_filter = [set_key] if set_key else list({i["set_key"] for i in issues})

        with self._driver.session() as session:
            rows = session.run(
                """
                UNWIND $issue_pairs AS pair
                MATCH (si:SemanticIssue {
                  set_key: pair.set_key, issue_id: pair.issue_id
                })
                MATCH (ri:ReasoningIssue {
                  scope:'INTEGRATED', set_key:si.set_key, chapter_id:si.chapter_id
                })-[:HAS_STEP]->(rs:ReasoningStep)-[:BASED_ON]->(a:Article)

                RETURN DISTINCT
                  a.scope       AS scope,
                  a.version_key AS version_key,
                  a.id          AS article_id,
                  a.title       AS article_title,
                  si.title      AS related_issue
                ORDER BY a.scope, a.id
                LIMIT 20
                """,
                {
                    "issue_pairs": [
                        {"set_key": i["set_key"], "issue_id": i["issue_id"]}
                        for i in issues
                        if i["set_key"] in sk_filter
                    ],
                },
            ).data()

        return rows

    def close(self) -> None:
        self._driver.close()
