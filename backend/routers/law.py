#29_FINAL/backend/routers/law.py
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Literal
import os
import json
import re
from datetime import datetime
from utils_B.normalize import normalize_article_input, to_article_id
from db.neo4j_client import driver

router = APIRouter()
Scope = Literal["LAW", "DECREE", "RULE"]

#==========================================================
# 법령 통합 뷰 API (Integrated Law View API)   
# ✅ snapshot
#==========================================================
@router.get("/snapshot/by-date")
def get_snapshot_by_date(as_of: str | None = None):
    # 디폴트: 오늘 (YYYYMMDD)
    if not as_of:
        as_of = datetime.today().strftime("%Y%m%d")

    # 공백/하이픈 제거
    as_of = as_of.strip().replace("-", "").replace(".", "").replace("/", "")

    # 6자리(YYMMDD)면 8자리로 보정 (20YYMMDD)
    if len(as_of) == 6 and as_of.isdigit():
        as_of = "20" + as_of

    if not (len(as_of) == 8 and as_of.isdigit()):
        raise HTTPException(status_code=400, detail="as_of must be YYYYMMDD or YYMMDD digits")

    query = """
    MATCH (s:IntegratedSnapshot {scope:"INTEGRATED"})
    WHERE toInteger(s.valid_from) <= toInteger($as_of)
      AND (s.valid_to IS NULL OR toInteger(s.valid_to) > toInteger($as_of))
    RETURN
      s.set_key AS set_key,
      s.valid_from AS valid_from,
      s.valid_to AS valid_to,
      s.promulgated_at AS promulgated_at,
      s.effective_at AS effective_at
    ORDER BY toInteger(s.effective_at) DESC
    LIMIT 1
    """

    with driver.session() as session:
        r = session.run(query, as_of=as_of).single()

    if not r:
        return None

    return {
        "set_key": r["set_key"],
        "valid_from": str(r["valid_from"]) if r["valid_from"] else None,
        "valid_to": str(r["valid_to"]) if r["valid_to"] else None,
        "promulgated_at": str(r["promulgated_at"]) if r["promulgated_at"] else None,
        "effective_at": str(r["effective_at"]) if r["effective_at"] else None,
    }

@router.get("/snapshots")
def list_law_snapshots():
    query = """
    MATCH (s:IntegratedSnapshot {scope:"INTEGRATED"})
    RETURN
      s.set_key AS set_key,
      s.valid_from AS valid_from,
      s.valid_to AS valid_to,
      s.promulgated_at AS promulgated_at,
      s.effective_at AS effective_at
    ORDER BY s.effective_at DESC
    """

    with driver.session() as session:
        result = session.run(query)
        snapshots = []
        for r in result:
            snapshots.append(
                {
                    "set_key": r["set_key"],
                    "valid_from": str(r["valid_from"]) if r["valid_from"] else None,
                    "valid_to": str(r["valid_to"]) if r["valid_to"] else None,
                    "promulgated_at": (
                        str(r["promulgated_at"]) if r["promulgated_at"] else None
                    ),
                    "effective_at": (
                        str(r["effective_at"]) if r["effective_at"] else None
                    ),
                }
            )

    return snapshots

# ---------------------------------------------------------
# ✅ chapter 챕터 그래프 API   
# ---------------------------------------------------------    
# 공통 유틸 Neo4j 결과를 **그래프 JSON(nodes/edges)**로 바꾸는 최소 유틸
def add_node(nodes, node_id, node_type, label=None, meta=None):
    if node_id not in nodes:
        nodes[node_id] = {
            "id": node_id,
            "type": node_type,
            "label": label or node_id,
            "meta": meta or {},
        }


def add_edge(edges, src, dst, edge_type):
    edges.append({"from": src, "to": dst, "type": edge_type})


"""
CH_2
LAW_20251001_21065__DECREE_20251128_35882__RULE_20250321_01114
1️⃣ 메인 그래프 (대표 화면)
Reasoning ↔ Semantic ↔ Article를 한 번에.
"""
@router.get("/chapters/{chapter_id}/graph")
def get_chapter_graph(chapter_id: str, set_key: str):
    query = """
    MATCH (ic:IntegratedChapter {
      scope:"INTEGRATED",
      set_key:$set_key,
      chapter_id:$chapter_id
    })
    OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_REASONING]->(ri)
    OPTIONAL MATCH (ri)-[:ALIGNED_WITH]->(sem)
    OPTIONAL MATCH (ri)-[:HAS_STEP]->(rs)
    OPTIONAL MATCH (rs)-[:BASED_ON]->(a)
    WITH ic, ri, sem, rs, collect(DISTINCT a) AS articles
    RETURN ic, ri, sem, rs, articles
    """

    nodes = {}
    edges = []

    with driver.session() as session:
        for r in session.run(query, set_key=set_key, chapter_id=chapter_id):
            ic = r["ic"]
            ri = r["ri"]
            sem = r["sem"]
            rs = r["rs"]
            articles = r["articles"]

            # IntegratedChapter
            if ic:
                add_node(
                    nodes,
                    ic.id,
                    "IntegratedChapter",
                    ic.get("name") or ic.get("chapter_id"),
                    {
                        "chapter_id": ic.get("chapter_id"),
                        "name": ic.get("name"),
                    }
                )


            # ReasoningIssue
            if ri:
                add_node(
                    nodes,
                    ri.id,
                    "ReasoningIssue",
                    ri.get("issue_title"),
                )
                add_edge(edges, ic.id, ri.id, "HAS_REASONING")

            # SemanticIssue
            if sem:
                add_node(
                    nodes,
                    sem.id,
                    "SemanticIssue",
                    sem.get("issue_id"),
                    {
                        "issue_id": sem.get("issue_id"),
                    }
                )
                add_edge(edges, ri.id, sem.id, "ALIGNED_WITH")

            # ReasoningStep (🔥 핵심: Article이 없어도 무조건 생성)
            if rs:
                add_node(
                    nodes,
                    rs.id,
                    "ReasoningStep",
                    f"Step {rs.get('step_id')}",
                    {"type": rs.get("step_type")},
                )
                add_edge(edges, ri.id, rs.id, "HAS_STEP")

                # Step → Articles (여러 개 가능)
                for a in articles:
                    if not a:
                        continue

                    article_label = (
                        a.get("title")
                        or a.get("article_number")
                        or a.get("article_no")
                        or f"Article {a.id}"
                    )

                    add_node(
                        nodes,
                        a.id,
                        "Article",
                        article_label,
                            {
                                "scope": a.get("scope") or a.get("source_type") or "LAW"
                            }
                        )
                    add_edge(edges, rs.id, a.id, "BASED_ON")

    return {
        "snapshot": {
            "set_key": set_key,
            "chapter_id": chapter_id,
            "view": "MAIN_GRAPH",
        },
        "nodes": list(nodes.values()),
        "edges": edges,
    }



# 2️⃣ 구조 뷰 (Structure)
@router.get("/chapters/{chapter_id}/structure")
def get_structure(chapter_id: str, set_key: str):
    query = """
    MATCH (s:IntegratedSnapshot {set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic:IntegratedChapter {chapter_id:$chapter_id})
      -[:DERIVED_FROM]->(c:Chapter)

    // 🔹 보조 정보: Law / LawVersion (그래프 축 아님)
    OPTIONAL MATCH (lv:LawVersion {scope:c.scope, version_key:c.version_key})-[:HAS_CHAPTER]->(c)
    OPTIONAL MATCH (law:Law {scope:c.scope, id:lv.law_id})-[:HAS_VERSION]->(lv)

    OPTIONAL MATCH (c)-[:HAS_SECTION]->(sec:Section)
    OPTIONAL MATCH (sec)-[:HAS_SUBDIVISION]->(sd:Subdivision)

    OPTIONAL MATCH (c)-[:HAS_ARTICLE]->(a1:Article)
    OPTIONAL MATCH (sec)-[:HAS_ARTICLE]->(a2:Article)
    OPTIONAL MATCH (sd)-[:HAS_ARTICLE]->(a3:Article)

    RETURN ic, c, law, sec, sd, a1, a2, a3
    """

    nodes: dict = {}
    edges: list = []

    def add_edge(src, dst, typ):
        if not src or not dst:
            return
        eid = f"{src.id}->{dst.id}:{typ}"
        edges.append({
            "from": src.id,
            "to": dst.id,
            "type": typ,
            "id": eid,
        })

    with driver.session() as session:
        for r in session.run(query, set_key=set_key, chapter_id=chapter_id):
            ic  = r["ic"]
            c   = r["c"]
            law = r["law"]
            sec = r["sec"]
            sd  = r["sd"]
            a1  = r["a1"]
            a2  = r["a2"]
            a3  = r["a3"]

            # 1️⃣ IntegratedChapter (기존 로직 유지)
            if ic:
                add_node(
                    nodes,
                    ic.id,
                    "IntegratedChapter",
                    ic.get("name") or ic.get("chapter_id"),
                    meta={
                        "chapter_id": ic.get("chapter_id"),
                        "name": ic.get("name"),
                    },
                )

            # 2️⃣ Chapter (🔥 여기서만 LAW 정보 흡수)
            if c:
                add_node(
                    nodes,
                    c.id,
                    "Chapter",
                    c.get("name") or c.get("chapter_id"),
                    meta={
                        "chapter_id": c.get("id"),              # CH_1
                        "title": c.get("name"),
                        "scope": c.get("scope"),                # LAW / DECREE / RULE
                        "law_name": law.get("name") if law else None,
                        "law_scope": law.get("scope") if law else None,
                    },
                )

            # 3️⃣ Section / Subdivision (기존 유지)
            if sec:
                add_node(
                    nodes,
                    sec.id,
                    "Section",
                    sec.get("name") or sec.get("id"),
                )

            if sd:
                add_node(
                    nodes,
                    sd.id,
                    "Subdivision",
                    sd.get("name") or sd.get("id"),
                )

            # 4️⃣ Articles (기존 유지)
            for a in [a1, a2, a3]:
                if a:
                    add_node(
                        nodes,
                        a.id,
                        "Article",
                        a.get("title")
                        or a.get("article_number")
                        or a.get("article_no")
                        or f"Article {a.id}",
                    )

            # ===== edges (절대 기존 구조 안 깨기) =====
            add_edge(ic, c, "IC_DERIVED_FROM_CHAPTER")
            add_edge(c, sec, "HAS_SECTION")
            add_edge(sec, sd, "HAS_SUBDIVISION")

            add_edge(c, a1, "HAS_ARTICLE")
            add_edge(sec, a2, "HAS_ARTICLE")
            add_edge(sd, a3, "HAS_ARTICLE")

    return {
        "snapshot": {"set_key": set_key, "chapter_id": chapter_id},
        "nodes": list(nodes.values()),
        "edges": edges,
    }

@router.get("/chapters")
def get_chapters(set_key: str):
    query = """
    MATCH (s:IntegratedSnapshot {set_key:$set_key})
    -[:HAS_INTEGRATED_CHAPTER]->(ic)
    RETURN DISTINCT
    ic.chapter_id AS chapter_id,
    ic.name AS title
    ORDER BY chapter_id

    """
    chapters = []

    with driver.session() as session:
        for r in session.run(query, set_key=set_key):
            chapters.append({
            "chapter_id": r["chapter_id"],
            "title": r["title"],
            })

    return chapters

# ---------------------------------------------------------
# ✅ chapter 챕터 텍스트 API    
# 3️⃣ 쟁점 뷰 (Semantic)
# ✅ semantic / reasoning (cache read-only)
# ---------------------------------------------------------
@router.get("/chapters/{chapter_id}/semantic")
def get_chapter_semantic(chapter_id: str, set_key: str):
    """
    Semantic (쟁점) 텍스트 전용 API
    - 그래프와 완전히 분리
    - cache 기반 read-only
    """

    base_dir = "cache/ITCL_integrated"
    semantic_path = os.path.join(
        base_dir,
        set_key,
        "02_semantic_dict.json"
    )

    if not os.path.exists(semantic_path):
        # 🔴 명확한 상태 코드
        return JSONResponse(
            status_code=404,
            content={
                "chapter_id": chapter_id,
                "chapter_name": None,
                "chapter_summary": None,
                "issues": [],
                "error": "semantic file not found",
            },
        )

    with open(semantic_path, "r", encoding="utf-8") as f:
        all_data = json.load(f)

    chapter_data = all_data.get(chapter_id)

    if not chapter_data:
        return JSONResponse(
            status_code=404,
            content={
                "chapter_id": chapter_id,
                "chapter_name": None,
                "chapter_summary": None,
                "issues": [],
                "error": "chapter semantic not found",
            },
        )

    # ✅ 정상 응답
    return {
        "chapter_id": chapter_id,
        "chapter_name": chapter_data.get("chapter_name"),
        "chapter_summary": chapter_data.get("chapter_summary"),
        "issues": chapter_data.get("issues", []),
    }

# 3️⃣-2 검토 단계 뷰 (Reasoning)
@router.get("/chapters/{chapter_id}/reasoning")
def get_chapter_reasoning(chapter_id: str, set_key: str):
    """
    Reasoning (검토 단계) 텍스트 전용 API
    - Semantic API와 동일한 패턴
    - cache 기반 read-only
    """

    base_dir = "cache/ITCL_integrated"
    reasoning_path = os.path.join(
        base_dir,
        set_key,
        "03_reasoning_dict.json"
    )

    if not os.path.exists(reasoning_path):
        return JSONResponse(
            status_code=404,
            content={
                "chapter_id": chapter_id,
                "chapter_name": None,
                "reasoning": [],
                "error": "reasoning file not found",
            },
        )

    with open(reasoning_path, "r", encoding="utf-8") as f:
        all_data = json.load(f)

    chapter_data = all_data.get(chapter_id)

    if not chapter_data:
        return JSONResponse(
            status_code=404,
            content={
                "chapter_id": chapter_id,
                "chapter_name": None,
                "reasoning": [],
                "error": "chapter reasoning not found",
            },
        )

    # ✅ 정상 응답
    return {
        "chapter_id": chapter_id,
        "chapter_name": chapter_data.get("chapter_name"),
        "reasoning": chapter_data.get("reasoning", []),
    }


# ---------------------------------------------------------
# ✅ 조문 텍스트 API    
# 조문 정독용 (항/호/목 포함) 
#---------------------------------------------------------

@router.get("/norm/article")
def get_norm_article(
    law_name: str,
    version_key: str,
    article_id: str,
):
    """
    조문 정독용 (항/호/목 포함)
    cache/{law_name}/{version_key}/01_norm_enriched.json 기반
    """

    base_dir = f"cache/{law_name}/{version_key}"
    json_path = os.path.join(base_dir, "01_norm_enriched.json")

    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="norm json not found")

    with open(json_path, "r", encoding="utf-8") as f:
        law_json = json.load(f)

    def find_article(law_json, article_id):
        for ch in law_json.get("chapters", []):
            for art in ch.get("articles", []):
                if art.get("id") == article_id:
                    return art
            for sec in ch.get("sections", []):
                for art in sec.get("articles", []):
                    if art.get("id") == article_id:
                        return art
                for sub in sec.get("subdivisions", []):
                    for art in sub.get("articles", []):
                        if art.get("id") == article_id:
                            return art
        return None

    article = find_article(law_json, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="article not found")

    return {
        "law_name": law_name,
        "version_key": version_key,
        "article": {
            "id": article["id"],
            "title": article.get("title"),
            "raw_text": article.get("raw_text"),
            "reference_notes": article.get("reference_notes"),
            "effective_date": article.get("effective_date"),
        },
        "paragraphs": article.get("paragraphs", []),
        "norm_units": article.get("norm_units", []),
    }

# ---------------------------------------------------------
# ✅ 조문 텍스트 API    
# 4️⃣ 역조문 조회, 근거 뷰 (ReasoningStep→Article)
# ---------------------------------------------------------

@router.get("/articles/{article_id}/reverse/full")
def reverse_lookup_article_full(
    article_id: str,
    set_key: str = Query(...),
    scope: str = Query(..., pattern="^(LAW|DECREE|RULE)$"),
    law_name: str = Query(...),
    version_key: str = Query(...),
):
    """
    특정 set_key 기준
    (Article[scope+version_key+id]) ← ReasoningStep 역조문 조회
    - 핵심: Article에서 시작해서 BASED_ON만으로 역추적한다.
    - Neo4j에서 직접 돌린 MATCH (a)<-[:BASED_ON]-(rs) 경로와 1:1 동일.
    """

    query = """
    MATCH (a:Article {
      id: $article_id,
      scope: $scope,
      version_key: $version_key
    })

    MATCH (rs:ReasoningStep {
      scope: "INTEGRATED",
      set_key: $set_key
    })-[:BASED_ON]->(a)

    MATCH (ri:ReasoningIssue {
      scope: "INTEGRATED",
      set_key: $set_key
    })-[:HAS_STEP]->(rs)

    RETURN
      $scope        AS scope,
      $law_name     AS law_name,
      $version_key  AS version_key,
      rs.chapter_id AS chapter_id,
      ri.issue_title AS issue_title,
      rs.step_id    AS step_id,
      rs.step_type  AS step_type,
      rs.description AS description
    ORDER BY
      rs.chapter_id,
      ri.issue_title,
      toInteger(rs.step_id)
    """

    with driver.session() as session:
        rows = session.run(
            query,
            article_id=article_id,
            set_key=set_key,
            scope=scope,
            law_name=law_name,
            version_key=version_key,
        ).data()

    return {
        "article_id": article_id,
        "set_key": set_key,
        "count": len(rows),
        "usages": rows,
    }



def iter_all_articles(law_json: Dict[str, Any]):
    for ch in law_json.get("chapters", []) or []:
        for art in ch.get("articles", []) or []:
            yield art
        for sec in ch.get("sections", []) or []:
            for art in sec.get("articles", []) or []:
                yield art
            for sub in sec.get("subdivisions", []) or []:
                for art in sub.get("articles", []) or []:
                    yield art


def load_norm_json(law_name: str, version_key: str) -> Dict[str, Any]:
    base_dir = f"cache/{law_name}/{version_key}"
    json_path = os.path.join(base_dir, "01_norm_enriched.json")

    if not os.path.exists(json_path):
        raise FileNotFoundError(json_path)

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_scope_versions_from_snapshot(set_key: str) -> List[Dict[str, str]]:
    query = """
    MATCH (snap:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
    MATCH (snap)-[:HAS_INTEGRATED_CHAPTER]->(ic)
    MATCH (ic)-[:DERIVED_FROM]->(c:Chapter)
    MATCH (c)<-[:HAS_CHAPTER]-(v:LawVersion)<-[:HAS_VERSION]-(l:Law)
    RETURN DISTINCT
      l.source_type AS scope,
      l.name        AS law_name,
      v.version_key AS version_key
    ORDER BY scope
    """
    with driver.session() as session:
        rows = session.run(query, set_key=set_key).data()

    out: List[Dict[str, str]] = []
    for r in rows:
        scope = str(r.get("scope") or "").upper()
        if scope not in ("LAW", "DECREE", "RULE"):
            continue
        law_name = str(r.get("law_name") or "").strip()
        version_key = str(r.get("version_key") or "").strip()
        if law_name and version_key:
            out.append(
                {
                    "scope": scope,
                    "law_name": law_name,
                    "version_key": version_key,
                }
            )

    if not out:
        raise HTTPException(status_code=404, detail="no law versions found for set_key")
    
    SCOPE_ORDER = {
    "LAW": 0,
    "DECREE": 1,
    "RULE": 2,
    }
    # 법적 위계 순서로 결과를 정렬 (LAW → DECREE → RULE)
    out.sort(key=lambda r: SCOPE_ORDER.get(r["scope"], 99))
    return out



# ---------------------------------------------------------
# ✅ 조문 텍스트 API    
# 4️⃣ 역조문 조회, 근거 뷰 (ReasoningStep→Article)    
# ---------------------------------------------------------

@router.get("/articles/resolve")
def resolve_articles(
    set_key: str = Query(..., description="IntegratedSnapshot.set_key"),
    q: str = Query(..., description='article input: "65", "65의2", "65조" 등'),
):
    normalized = normalize_article_input(q)
    if not normalized:
        raise HTTPException(status_code=400, detail="invalid article input")

    target_id = to_article_id(normalized)
    is_exact = "_" in normalized

    scope_versions = get_scope_versions_from_snapshot(set_key)

    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for sv in scope_versions:
        scope: Scope = sv["scope"]  # type: ignore
        law_name = sv["law_name"]
        version_key = sv["version_key"]

        try:
            law_json = load_norm_json(law_name, version_key)
        except FileNotFoundError as e:
            errors.append(
                {
                    "scope": scope,
                    "law_name": law_name,
                    "version_key": version_key,
                    "error": f"norm json not found: {str(e)}",
                }
            )
            continue

        matched: List[Dict[str, Any]] = []

        if is_exact:
            for art in iter_all_articles(law_json):
                if art.get("id") == target_id:
                    matched.append(
                        {
                            "article_id": art.get("id"),
                            "title": art.get("title"),
                            "effective_date": art.get("effective_date"),
                        }
                    )
                    break
        else:
            for art in iter_all_articles(law_json):
                aid = str(art.get("id") or "")
                if aid == target_id or aid.startswith(f"{target_id}_"):
                    matched.append(
                        {
                            "article_id": aid,
                            "title": art.get("title"),
                            "effective_date": art.get("effective_date"),
                        }
                    )

            def sort_key(a: Dict[str, Any]):
                m = re.match(r"^ART_(\d+)(?:_(\d+))?$", a["article_id"])
                if not m:
                    return (10**9, 10**9)
                return (int(m.group(1)), int(m.group(2) or 0))

            matched.sort(key=sort_key)

        results.append(
            {
                "scope": scope,
                "law_name": law_name,
                "version_key": version_key,
                "matched": matched,
            }
        )

    return {
        "set_key": set_key,
        "query": q,
        "normalized": normalized,
        "target_article_id": target_id,
        "match_mode": "EXACT" if is_exact else "PREFIX",
        "results": results,
        "errors": errors,
    }
