# db/graph_search.py
"""
그래프 + 벡터 하이브리드 검색 엔진

세 가지 검색 모드:
  1. search_similar_issues   — 쟁점 의미 유사도 (벡터)
  2. get_statute_cases       — 법령 기반 판례 탐색 (그래프)
  3. analyze_winning_patterns — 승소 패턴 분석 (하이브리드)
"""

import os

import openai
from neo4j import GraphDatabase

EMBED_MODEL = "text-embedding-3-small"


def _embed(text: str, client: openai.OpenAI) -> list[float]:
    return client.embeddings.create(model=EMBED_MODEL, input=[text]).data[0].embedding


class LegalGraphSearch:

    def __init__(self):
        self._driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
        )
        self._oai = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # ─────────────────────────────────────────────
    # 1. 벡터 유사도 검색 — 쟁점
    # ─────────────────────────────────────────────

    def search_similar_issues(self, query: str, top_k: int = 5) -> list[dict]:
        """
        자연어 쿼리와 의미적으로 유사한 쟁점을 가진 판례를 반환합니다.
        예) "특수관계자간 자산 저가양도가 부당행위계산 부인 대상인지"
        """
        embedding = _embed(query, self._oai)

        with self._driver.session() as session:
            rows = session.run(
                """
                CALL db.index.vector.queryNodes('issue_embedding', $top_k, $embedding)
                YIELD node AS i, score
                MATCH (c:Case)-[:HAS_ISSUE]->(i)
                RETURN c.case_id        AS case_id,
                       c.case_number    AS case_number,
                       c.court_name     AS court_name,
                       c.judgment_date  AS judgment_date,
                       c.conclusion     AS conclusion,
                       i.issue          AS issue,
                       i.rule           AS rule,
                       i.mini_conclusion AS mini_conclusion,
                       round(score, 4)  AS similarity
                ORDER BY score DESC
                """,
                {"top_k": top_k, "embedding": embedding},
            )
            return [dict(r) for r in rows]

    # ─────────────────────────────────────────────
    # 2. 그래프 트래버설 — 법령 기반 판례 탐색
    # ─────────────────────────────────────────────

    def get_statute_cases(self, statute_name: str) -> list[dict]:
        """
        특정 법령을 인용한 판례와 쟁점을 시계열순으로 반환합니다.
        예) "국세기본법", "법인세법", "부가가치세법"
        """
        with self._driver.session() as session:
            rows = session.run(
                """
                MATCH (c:Case)-[:HAS_ISSUE]->(i:IssueChain)-[:CITES_STATUTE]->(s:Statute)
                WHERE s.name CONTAINS $name
                RETURN c.case_id        AS case_id,
                       c.case_number    AS case_number,
                       c.court_name     AS court_name,
                       c.judgment_date  AS judgment_date,
                       c.conclusion     AS conclusion,
                       i.issue          AS issue,
                       i.rule           AS rule,
                       i.mini_conclusion AS mini_conclusion,
                       s.name           AS statute,
                       s.provision      AS provision
                ORDER BY c.judgment_date ASC
                """,
                {"name": statute_name},
            )
            return [dict(r) for r in rows]

    # ─────────────────────────────────────────────
    # 3. 하이브리드 — 승소 패턴 분석
    # ─────────────────────────────────────────────

    def analyze_winning_patterns(self, query: str, top_k: int = 10) -> dict:
        """
        유사 쟁점 판례들을 검색한 뒤, 각 판례의 결론과 적용 법리를
        취합하여 승소/패소 패턴 분석 데이터를 반환합니다.

        반환 구조:
          similar_issues  — 유사 쟁점 + 판례 정보 (유사도 포함)
          related_cases   — 판례별 결론 + 적용 법리 전체 목록
          statutes_cited  — 해당 판례군에서 가장 많이 인용된 법령
        """
        similar = self.search_similar_issues(query, top_k=top_k)
        case_ids = list({r["case_id"] for r in similar})

        with self._driver.session() as session:
            # 판례별 결론 + 법리 수집
            case_rows = session.run(
                """
                MATCH (c:Case)-[:HAS_ISSUE]->(i:IssueChain)
                WHERE c.case_id IN $ids
                RETURN c.case_id       AS case_id,
                       c.case_number   AS case_number,
                       c.court_name    AS court_name,
                       c.judgment_date AS judgment_date,
                       c.conclusion    AS conclusion,
                       collect(i.issue)           AS issues,
                       collect(i.rule)            AS rules,
                       collect(i.mini_conclusion) AS mini_conclusions
                ORDER BY c.judgment_date ASC
                """,
                {"ids": case_ids},
            )
            related_cases = [dict(r) for r in case_rows]

            # 가장 많이 인용된 법령
            statute_rows = session.run(
                """
                MATCH (c:Case)-[:HAS_ISSUE]->(i:IssueChain)-[:CITES_STATUTE]->(s:Statute)
                WHERE c.case_id IN $ids
                RETURN s.name AS statute, count(*) AS freq
                ORDER BY freq DESC
                LIMIT 10
                """,
                {"ids": case_ids},
            )
            statutes_cited = [dict(r) for r in statute_rows]

        return {
            "query":          query,
            "similar_issues": similar,
            "related_cases":  related_cases,
            "statutes_cited": statutes_cited,
        }

    # ─────────────────────────────────────────────
    # 4. 시계열 트렌드 — 연도·법원별 승소율 집계
    # ─────────────────────────────────────────────

    def get_trend_data(self, query: str, start_year: int = 2000, end_year: int = 2030, top_k: int = 50) -> dict:
        """
        유사 쟁점 판례들의 연도별·법원별 납세자 승소율을 집계합니다.
        """
        similar = self.search_similar_issues(query, top_k=top_k)
        case_ids = list({r["case_id"] for r in similar})

        with self._driver.session() as session:
            rows = session.run(
                """
                MATCH (c:Case)
                WHERE c.case_id IN $ids
                  AND c.judgment_date >= $start
                  AND c.judgment_date <= $end
                RETURN c.judgment_date AS date,
                       c.court_name    AS court,
                       c.conclusion    AS conclusion,
                       c.case_number   AS case_number
                ORDER BY c.judgment_date ASC
                """,
                {
                    "ids": case_ids,
                    "start": str(start_year),
                    "end": str(end_year + 1),
                },
            )
            cases = [dict(r) for r in rows]

        year_stats: dict[str, dict] = {}
        for c in cases:
            year = (c.get("date") or "")[:4]
            if not year.isdigit():
                continue
            if year not in year_stats:
                year_stats[year] = {"total": 0, "taxpayer_win": 0, "cases": []}
            year_stats[year]["total"] += 1
            conclusion = (c.get("conclusion") or "").lower()
            if any(k in conclusion for k in ["납세자 승소", "원고 승", "취소", "인용"]):
                year_stats[year]["taxpayer_win"] += 1
            year_stats[year]["cases"].append(c["case_number"])

        for y, s in year_stats.items():
            s["win_rate"] = round(s["taxpayer_win"] / s["total"] * 100, 1) if s["total"] else 0

        return {
            "query": query,
            "year_stats": dict(sorted(year_stats.items())),
            "total_cases": len(cases),
            "similar_issues": similar,
        }

    def close(self) -> None:
        self._driver.close()
