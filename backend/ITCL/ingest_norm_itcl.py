#ITCL/ingest_norm_itcl.py
from neo4j import GraphDatabase
import os
import dotenv
import neo4j
dotenv.load_dotenv()

#.\neo4j.bat console
URI = os.getenv("NEO4J_URI", "neo4j+s://3dfa7316.databases.neo4j.io")
AUTH = ("neo4j", os.getenv("NEO4J_PASSWORD", "password"))

driver = neo4j.GraphDatabase.driver(URI, auth=AUTH)


# -----------------------------
# 8) 전체 run-ingest
# -----------------------------

# -----------------------------
# ✅ run_ingest_norm (구조 유지: execute_write 순서 그대로)
#   - 변경: scope/vkey를 run_ingest_norm에서 계산 후 인자로 전달
# -----------------------------
def run_ingest_norm(law_json):
    scope = norm_scope(law_json)
    vkey  = version_key(law_json)

    with driver.session() as session:
        # (1) Law + LawVersion (NEW)
        session.execute_write(ingest_law, law_json, scope)                 # Law(불변)만
        session.execute_write(ingest_law_version, law_json, scope, vkey)   # LawVersion(버전 앵커)

        # (2) 이하 기존 순서 유지, 단 vkey 전달
        session.execute_write(ingest_chapters, law_json, scope, vkey)
        session.execute_write(ingest_addenda, law_json, scope, vkey)
        session.execute_write(ingest_revision_reasons, law_json, scope, vkey)
        session.execute_write(ingest_amendments, law_json, scope, vkey)
        session.execute_write(ingest_annexes, law_json, scope, vkey)

# -----------------------------
# 제약조건
# -----------------------------

"""
// Law (불변 앵커): 기존 유지 or 재생성
CREATE CONSTRAINT law_key IF NOT EXISTS
FOR (l:Law)
REQUIRE (l.scope, l.id) IS UNIQUE;

// LawVersion (버전 앵커)
CREATE CONSTRAINT law_version_key IF NOT EXISTS
FOR (v:LawVersion)
REQUIRE (v.scope, v.law_id, v.version_key) IS UNIQUE;

CREATE CONSTRAINT chapter_key IF NOT EXISTS
FOR (c:Chapter)
REQUIRE (c.scope, c.version_key, c.id) IS UNIQUE;

CREATE CONSTRAINT section_key IF NOT EXISTS
FOR (s:Section)
REQUIRE (s.scope, s.version_key, s.id) IS UNIQUE;

CREATE CONSTRAINT subdivision_key IF NOT EXISTS
FOR (sd:Subdivision)
REQUIRE (sd.scope, sd.version_key, sd.id) IS UNIQUE;

CREATE CONSTRAINT article_key IF NOT EXISTS
FOR (a:Article)
REQUIRE (a.scope, a.version_key, a.id) IS UNIQUE;

CREATE CONSTRAINT paragraph_key IF NOT EXISTS
FOR (p:Paragraph)
REQUIRE (p.scope, p.version_key, p.id) IS UNIQUE;

CREATE CONSTRAINT item_key IF NOT EXISTS
FOR (i:Item)
REQUIRE (i.scope, i.version_key, i.id) IS UNIQUE;

CREATE CONSTRAINT subitem_key IF NOT EXISTS
FOR (si:SubItem)
REQUIRE (si.scope, si.version_key, si.id) IS UNIQUE;

CREATE CONSTRAINT addenda_key IF NOT EXISTS
FOR (ad:Addenda)
REQUIRE (ad.scope, ad.version_key, ad.id) IS UNIQUE;

CREATE CONSTRAINT normunit_key IF NOT EXISTS
FOR (n:NormUnit)
REQUIRE (n.scope, n.version_key, n.id) IS UNIQUE;

CREATE CONSTRAINT crossref_key IF NOT EXISTS
FOR (r:CrossRef)
REQUIRE (r.scope, r.version_key, r.from_id, r.target, r.type) IS UNIQUE;

CREATE CONSTRAINT lawtarget_key IF NOT EXISTS
FOR (t:LawTarget)
REQUIRE (t.scope, t.version_key, t.name) IS UNIQUE;

CREATE CONSTRAINT semantic_issue_key IF NOT EXISTS
FOR (s:SemanticIssue)
REQUIRE (s.scope, s.version_key, s.id) IS UNIQUE;

CREATE CONSTRAINT reasoning_issue_key IF NOT EXISTS
FOR (r:ReasoningIssue)
REQUIRE (r.scope, r.version_key, r.id) IS UNIQUE;

CREATE CONSTRAINT reasoning_step_key IF NOT EXISTS
FOR (st:ReasoningStep)
REQUIRE (st.scope, st.version_key, st.id) IS UNIQUE;

CREATE INDEX lawversion_current_lookup IF NOT EXISTS
FOR (v:LawVersion)
ON (v.scope, v.law_id, v.is_current);

CREATE INDEX chapter_by_version IF NOT EXISTS
FOR (c:Chapter)
ON (c.scope, c.version_key, c.id);


"""

# -----------------------------
# 0) 기본 쿼리 생성기 
# -----------------------------
def run_query(query, params=None):
    with driver.session() as session:
        return session.run(query, params).data()
    
    
def reset_db():
    run_query("MATCH (n) DETACH DELETE n")


def version_key(law: dict) -> str:
    meta = law.get("metadata", {})
    d = meta.get("공포일자")
    n = meta.get("공포번호")
    if not d or not n:
        raise ValueError("공포일자/공포번호 없음 → version_key 생성 불가")
    return f"{d}_{n}"


def norm_scope(law_json: dict) -> str:
    st = law_json.get("source_type")

    if st == "LAW":
        return "LAW"
    if st == "DECREE":
        return "DECREE"
    if st == "RULE":
        return "RULE"

    raise ValueError(f"[INGEST BLOCKED] Unknown source_type: {st}")


def normalize_text(v):
    if isinstance(v, list):
        flat = []
        for x in v:
            if isinstance(x, list):
                flat.extend(x)
            else:
                flat.append(x)
        return " ".join([str(x).strip() for x in flat])
    return v

# -----------------------------
# 1. ingest_law 구조부터 시작
# -----------------------------
# (Law {id: "000603", name: "국제조세조정에 관한 법률"})

def ingest_law(tx, law, scope):
    scope = norm_scope(law)

    tx.run(
        """
        MERGE (l:Law {scope: $scope, id: $id})
        SET l.name = $name,
            l.source_type = $source_type,
            l.law_type = $law_type,
            l.ministry = $ministry
        """,
        scope=scope,
        id=law["law_id"],
        name=law["law_name"],
        source_type=law.get("source_type"),
        law_type=law["metadata"].get("법종구분"),
        ministry=law["metadata"].get("소관부처"),
    )

# -----------------------------
# ✅ NEW) LawVersion ingest (버전 앵커)
#   - LawVersion {scope, law_id, version_key} UNIQUE
#   - Law -[:HAS_VERSION]-> LawVersion
# -----------------------------

def ingest_law_version(tx, law, scope, vkey):
    meta = law.get("metadata", {})

    tx.run(
        """
        MERGE (v:LawVersion {
          scope: $scope,
          law_id: $law_id,
          version_key: $version_key
        })
        SET v.promulgation_date = $promulgation_date,
            v.promulgation_no   = $promulgation_no,
            v.effective_date    = $effective_date,
            v.is_current        = COALESCE(v.is_current, false) 
        WITH v
        MATCH (l:Law {scope:$scope, id:$law_id})
        MERGE (l)-[:HAS_VERSION]->(v)
        """,
        scope=scope,
        law_id=law["law_id"],
        version_key=vkey,
        promulgation_date=meta.get("공포일자"),
        promulgation_no=meta.get("공포번호"),
        effective_date=meta.get("시행일자"),
    )

# -----------------------------
# 2. Chapter ingest
# -----------------------------
def ingest_chapters(tx, law: dict, scope: str, vkey: str):
    for ch in law["chapters"]:
        tx.run(
            """
            MERGE (c:Chapter {
              scope:$scope,
              version_key:$version_key,
              id:$id
            })
            SET c.name = $name,
                c.domain = $domain
            WITH c
            MATCH (v:LawVersion {
              scope:$scope,
              law_id:$law_id,
              version_key:$version_key
            })
            MERGE (v)-[:HAS_CHAPTER]->(c)
            """,
            scope=scope,
            version_key=vkey,
            id=ch["id"],
            name=ch["name"],
            domain=ch.get("domain"),
            law_id=law["law_id"],
        )

        # 1) Chapter 직속 Article
        for art in ch.get("articles", []):
            ingest_article(tx, art, scope=scope, vkey=vkey, 
                           parent_label="Chapter", parent_id=ch["id"], 
                           rel="HAS_ARTICLE")

        # 2) Section
        ingest_sections(tx, scope=scope, vkey=vkey, chapter=ch)
        
# -----------------------------
# 3. Section ingest
# -----------------------------

def ingest_sections(tx, scope, vkey, chapter):
    for sec in chapter.get("sections", []):
        tx.run(
            """
            MERGE (s:Section {scope:$scope,  version_key:$version_key, id:$id})
            SET s.name = $name,
                s.domain = $domain
            WITH s
            MATCH (c:Chapter {scope:$scope, version_key:$version_key, id:$chapter_id})
            MERGE (c)-[:HAS_SECTION]->(s)
            """,
            scope=scope,
            version_key=vkey,
            id=sec["id"],
            name=sec["name"],
            chapter_id=chapter["id"],
            domain=sec.get("domain"),
        )

        ingest_articles_under_section(tx, scope=scope, vkey=vkey, section=sec)
        ingest_subdivisions(tx, scope=scope, vkey=vkey, section=sec)



# -----------------------------
# 4. Subdivision ingest
# -----------------------------

def ingest_subdivisions(tx, scope, vkey, section):
    for sub in section.get("subdivisions", []):
        tx.run(
            """
            MERGE (sd:Subdivision {scope:$scope, version_key:$version_key, id:$id})
            SET sd.name = $name,
                sd.domain = $domain
            WITH sd
            MATCH (s:Section {scope:$scope, version_key:$version_key, id:$section_id})
            MERGE (s)-[:HAS_SUBDIVISION]->(sd)
            """,
            scope=scope,
            version_key=vkey,
            id=sub["id"],
            name=sub["name"],
            section_id=section["id"],
            domain=sub.get("domain"),
        )

        ingest_articles_under_sub(tx, scope=scope, vkey=vkey, subdivision=sub)


# -----------------------------
# 5) Article ingest
#   - 기존 필드(reference_notes 포함) 절대 삭제/변경 없음
#   - 변경: Article MERGE 키에 version_key 포함
#   - 변경: parent MATCH에도 version_key 포함
# -----------------------------
def ingest_articles_under_section(tx, scope, vkey, section):
    for art in section.get("articles", []):
        ingest_article(
            tx, art,
            scope=scope, vkey=vkey,
            parent_label="Section", parent_id=section["id"],
            rel="HAS_ARTICLE"
        )

def ingest_articles_under_sub(tx, scope, vkey, subdivision):
    for art in subdivision.get("articles", []):
        ingest_article(
            tx, art,
            scope=scope, vkey=vkey,
            parent_label="Subdivision", parent_id=subdivision["id"],
            rel="HAS_ARTICLE"
        )

def ingest_article(tx, art, scope, vkey, parent_label, parent_id, rel):
    title = normalize_text(art.get("title"))
    raw_text = normalize_text(art.get("raw_text"))
    ref_notes = normalize_text(art.get("reference_notes"))  # ✅ 유지

    tx.run(
        f"""
        MERGE (a:Article {{scope:$scope, version_key:$version_key, id:$id}})
        SET a.title = $title,
            a.effective_date = $effective_date,
            a.changed = $changed,
            a.raw_text = $raw_text,
            a.reference_notes = $reference_notes,
            a.domain = $domain
        WITH a
        MATCH (p:{parent_label} {{scope:$scope, version_key:$version_key, id:$parent_id}})
        MERGE (p)-[:{rel}]->(a)
        """,
        scope=scope,
        version_key=vkey,
        id=art["id"],
        title=title,
        effective_date=art.get("effective_date"),
        changed=art.get("changed"),
        raw_text=raw_text,
        reference_notes=ref_notes,
        parent_id=parent_id,
        domain=art.get("domain"),
    )

    ingest_paragraphs(tx, scope=scope, vkey=vkey, art=art)
    ingest_norm_units(tx, scope=scope, vkey=vkey, article=art)
    ingest_cross_refs(tx, scope=scope, vkey=vkey, article=art)



# -----------------------------
# NormUnit ingest
#   - 변경: NormUnit MERGE 키에 version_key 포함
#   - 변경: NORM_UNIT_OF 연결 Article MATCH에도 version_key 포함
# -----------------------------

def ingest_norm_units(tx, scope, vkey, article):
    for nu in article.get("norm_units", []):
        nu_id = f"{scope}|{article['id']}|{nu['level']}|{nu['ref'].get('para_no') or '-'}|{nu['ref'].get('item_no') or '-'}|{nu['ref'].get('subitem_no') or '-'}"

        tx.run(
            """
            MERGE (n:NormUnit {scope:$scope, version_key:$version_key, id:$id})
            SET n.article_id = $article_id,
                n.level = $level,
                n.ref_para = $para,
                n.ref_item = $item,
                n.ref_subitem = $subitem,
                n.roles = $roles,
                n.short_label = $short_label
            """,
            scope=scope,
            version_key=vkey,
            id=nu_id,
            article_id=article["id"],
            level=nu["level"],
            para=nu["ref"].get("para_no"),
            item=nu["ref"].get("item_no"),
            subitem=nu["ref"].get("subitem_no"),
            roles=nu.get("roles", []),
            short_label=nu.get("short_label"),
        )

        tx.run(
            """
            MATCH (a:Article {scope:$scope, version_key:$version_key, id:$article_id})
            MATCH (n:NormUnit {scope:$scope, version_key:$version_key, id:$id})
            MERGE (n)-[:NORM_UNIT_OF]->(a)
            """,
            scope=scope,
            version_key=vkey,
            article_id=article["id"],
            id=nu_id,
        )

# -----------------------------
# CrossRef ingest
#   - 변경: CrossRef MERGE 키에 version_key 포함
#   - 변경: LawTarget MERGE 키에 version_key 포함
#   - 변경: NormUnit MATCH에도 version_key 포함
# -----------------------------
def ingest_cross_refs(tx, scope, vkey, article):
    for nu in article.get("norm_units", []):
        nu_id = f"{scope}|{article['id']}|{nu['level']}|{nu['ref'].get('para_no') or '-'}|{nu['ref'].get('item_no') or '-'}|{nu['ref'].get('subitem_no') or '-'}"

        for ref in nu.get("cross_refs", []):
            tx.run(
                """
                MERGE (r:CrossRef {scope:$scope, version_key:$version_key, from_id:$from_id, target:$target, type:$type})
                SET r.note = $note
                """,
                scope=scope,
                version_key=vkey,
                from_id=nu_id,
                target=ref["target"],
                type=ref["type"],
                note=ref.get("note"),
            )

            tx.run(
                """
                MATCH (n:NormUnit {scope:$scope, version_key:$version_key, id:$from_id})
                MERGE (t:LawTarget {scope:$scope, version_key:$version_key, name:$target})
                MERGE (n)-[:REFERS_TO {type:$type}]->(t)
                """,
                scope=scope,
                version_key=vkey,
                from_id=nu_id,
                target=ref["target"],
                type=ref["type"],
            )

# -----------------------------
# 6) Paragraph / Item / SubItem ingest
#   - 변경: 각 노드 MERGE 키 + parent MATCH 키에 version_key 포함
# -----------------------------
def ingest_paragraphs(tx, scope, vkey, art):
    for para in art.get("paragraphs", []):
        pid = f"{art['id']}_PARA_{para['para_no']}"

        tx.run(
            """
            MERGE (p:Paragraph {scope:$scope, version_key:$version_key, id:$id})
            SET p.text = $text,
                p.changed = $changed
            WITH p
            MATCH (a:Article {scope:$scope, version_key:$version_key, id:$article_id})
            MERGE (a)-[:HAS_PARAGRAPH]->(p)
            """,
            scope=scope,
            version_key=vkey,
            id=pid,
            text=normalize_text(para.get("text")),
            changed=para["changed"],
            article_id=art["id"],
        )

        ingest_items(tx, scope=scope, vkey=vkey, parent_pid=pid, para=para)

def ingest_items(tx, scope, vkey, parent_pid, para):
    for item in para.get("items", []):
        iid = f"{parent_pid}_ITEM_{item['item_no']}"

        tx.run(
            """
            MERGE (i:Item {scope:$scope, version_key:$version_key, id:$id})
            SET i.text = $text
            WITH i
            MATCH (p:Paragraph {scope:$scope, version_key:$version_key, id:$parent_pid})
            MERGE (p)-[:HAS_ITEM]->(i)
            """,
            scope=scope,
            version_key=vkey,
            id=iid,
            text=normalize_text(item.get("text")),
            parent_pid=parent_pid,
        )

        ingest_subitems(tx, scope=scope, vkey=vkey, parent_iid=iid, item=item)

def ingest_subitems(tx, scope, vkey, parent_iid, item):
    for sub in item.get("subitems", []):
        sid = f"{parent_iid}_SUB_{sub['subitem_no']}"

        tx.run(
            """
            MERGE (s:SubItem {scope:$scope, version_key:$version_key, id:$id})
            SET s.text = $text
            WITH s
            MATCH (i:Item {scope:$scope, version_key:$version_key, id:$parent_iid})
            MERGE (i)-[:HAS_SUBITEM]->(s)
            """,
            scope=scope,
            version_key=vkey,
            id=sid,
            text=normalize_text(sub.get("text")),
            parent_iid=parent_iid,
        )

# -----------------------------
# 7) addenda ingest (부칙)
#   - 변경: Addenda MERGE 키 + LawVersion 연결로 변경
#   - id 생성은 기존 유지
# -----------------------------
def ingest_addenda(tx, law, scope, vkey):
    for ad in law.get("addenda", []):
        aid = f"{law['law_id']}_ADDENDA_{ad['date']}"

        text = ad["content"]
        if isinstance(text, list):
            text = " ".join([str(x).strip() for x in text])

        tx.run(
            """
            MERGE (ad:Addenda {scope:$scope, version_key:$version_key, id:$id})
            SET ad.date = $date,
                ad.text = $text
            WITH ad
            MATCH (v:LawVersion {scope:$scope, law_id:$law_id, version_key:$version_key})
            MERGE (v)-[:HAS_ADDENDA]->(ad)
            """,
            scope=scope,
            version_key=vkey,
            id=aid,
            date=ad["date"],
            text=text,
            law_id=law["law_id"],
        )

# -----------------------------
# RevisionReason / Amendment / Annex
#   - 너가 올린 제약엔 없어도, 버전별 overwrite 방지 위해 version_key 포함 MERGE
#   - 연결도 LawVersion 기준으로 통일
# -----------------------------
def ingest_revision_reasons(tx, law, scope, vkey):
    for i, rr in enumerate(law.get("revision_reasons", []), start=1):
        rid = f"{law['law_id']}_REV_REASON_{i}"

        tx.run(
            """
            MERGE (r:RevisionReason {scope:$scope, version_key:$version_key, id:$id})
            SET r.text = $text
            WITH r
            MATCH (v:LawVersion {scope:$scope, law_id:$law_id, version_key:$version_key})
            MERGE (v)-[:HAS_REVISION_REASON]->(r)
            """,
            scope=scope,
            version_key=vkey,
            id=rid,
            text=rr.get("text"),
            law_id=law["law_id"],
        )

def ingest_amendments(tx, law, scope, vkey):
    for i, am in enumerate(law.get("amendments", []), start=1):
        aid = f"{law['law_id']}_AMEND_{i}"

        tx.run(
            """
            MERGE (a:Amendment {scope:$scope, version_key:$version_key, id:$id})
            SET a.text = $text
            WITH a
            MATCH (v:LawVersion {scope:$scope, law_id:$law_id, version_key:$version_key})
            MERGE (v)-[:HAS_AMENDMENT]->(a)
            """,
            scope=scope,
            version_key=vkey,
            id=aid,
            text=am.get("text"),
            law_id=law["law_id"],
        )

def ingest_annexes(tx, law, scope, vkey):
    for annex in law.get("annexes", []):
        ax_id = f"{law['law_id']}_{annex['id']}"

        tx.run(
            """
            MERGE (x:Annex {scope:$scope, version_key:$version_key, id:$id})
            SET x.number = $number,
                x.title = $title,
                x.content_raw = $content_raw,
                x.images = $images,
                x.pdf = $pdf,
                x.hwp = $hwp
            WITH x
            MATCH (v:LawVersion {scope:$scope, law_id:$law_id, version_key:$version_key})
            MERGE (v)-[:HAS_ANNEX]->(x)
            """,
            scope=scope,
            version_key=vkey,
            id=ax_id,
            number=annex.get("number"),
            title=annex.get("title"),
            content_raw=annex.get("content_raw"),
            images=annex.get("images", []),
            pdf=annex.get("pdf"),
            hwp=annex.get("hwp"),
            law_id=law["law_id"],
        )


if __name__ == "__main__":
    import json

    # 1) 최종 병합된 스키마 로드
    #(norm_units + cross_refs + article_summary 포함본)
    with open("ITCL_merged_with_summary.json", "r", encoding="utf-8") as f:
        law = json.load(f)

    # 2) DB 초기화
    print("🗑 Resetting database...")
    reset_db()

    # 3) ingest 실행
    print("📥 Ingesting into Neo4j (ITCL_reasoning_enriched)...")
    run_ingest_norm(law)

    print("🎉 Ingest 완료!")
