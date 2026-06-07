# db/graph_schema.py
"""
Neo4j 스키마 초기화 — 제약조건 · 인덱스 · 벡터 인덱스
IF NOT EXISTS 덕분에 재실행해도 안전 (idempotent)
"""

CONSTRAINTS = [
    "CREATE CONSTRAINT case_unique        IF NOT EXISTS FOR (c:Case)       REQUIRE c.case_id  IS UNIQUE",
    "CREATE CONSTRAINT issue_unique       IF NOT EXISTS FOR (i:IssueChain) REQUIRE i.uid      IS UNIQUE",
    "CREATE CONSTRAINT statute_unique     IF NOT EXISTS FOR (s:Statute)    REQUIRE s.id       IS UNIQUE",
    "CREATE CONSTRAINT keyword_unique     IF NOT EXISTS FOR (k:Keyword)    REQUIRE k.text     IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX case_court  IF NOT EXISTS FOR (c:Case)    ON (c.court_name)",
    "CREATE INDEX case_date   IF NOT EXISTS FOR (c:Case)    ON (c.judgment_date)",
    "CREATE INDEX statute_name IF NOT EXISTS FOR (s:Statute) ON (s.name)",
]

# Neo4j 5.x native vector index (cosine similarity, 1536-dim)
VECTOR_INDEXES = [
    """
    CREATE VECTOR INDEX issue_embedding IF NOT EXISTS
    FOR (i:IssueChain) ON i.embedding
    OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}
    """,
    """
    CREATE VECTOR INDEX case_narrative_embedding IF NOT EXISTS
    FOR (c:Case) ON c.narrative_embedding
    OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}
    """,
    """
    CREATE VECTOR INDEX itcl_issue_embedding IF NOT EXISTS
    FOR (si:SemanticIssue) ON si.embedding
    OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}
    """,
]


def init_schema(driver) -> None:
    """제약조건 + 인덱스 + 벡터 인덱스를 한번에 설정"""
    with driver.session() as session:
        for q in CONSTRAINTS + INDEXES + VECTOR_INDEXES:
            session.run(q)
    print("[schema] 초기화 완료")
