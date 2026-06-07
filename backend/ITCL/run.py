#ITCL/run.py
from typing import List, Optional, Dict
from ITCL.chain import (ArticleSummaryChain, NormUnitChain,
                        NormUnitCrossRefChain,ChapterSemanticChain,ChapterReasoningChain)
from ITCL.models import (ArticleSummaryInput,ArticleSummaryOutput,
                         NormUnitOutput,NormUnitInput,
                         NormUnitCrossRefInput, NormUnitCrossRefOutput,
                         ChapterSemanticInput,ChapterSemanticOutput, ChapterReasoningInput,ChapterReasoningOutput)
from ITCL.prompts import ARTICLE_SUMMARY, NORM_UNIT_PROMPT, CROSS_REF, CHAPTER_SEMANTICS
import os, json

  
def make_version_context(law):
    law_name = law["law_name"]
    meta = law["metadata"]

    promulgated_at = meta["공포일자"]
    promulgation_no = meta["공포번호"]

    ver_key = f"{promulgated_at}_{promulgation_no}"
    base_dir = f"cache/{law_name}/{ver_key}"

    os.makedirs(base_dir, exist_ok=True)

    return {
        "law_name": law_name,
        "promulgated_at": promulgated_at,
        "promulgation_no": promulgation_no,
        "base_dir": base_dir,
    }

def cache_path(ctx: dict, *paths) -> str:
    path = os.path.join(ctx["base_dir"], *paths)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path

def load_cache(ctx: dict, *paths):
    path = cache_path(ctx, *paths)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(ctx: dict, obj, *paths):
    path = cache_path(ctx, *paths)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path

# ---------------------------
# ★ Article Summary ★
# ---------------------------
def process_article(art,ctx, law_json, chain):
    article_id = art["id"]
    cached = load_cache(ctx, "article_summaries", f"{article_id}.json")
    if cached:
        return ArticleSummaryOutput(**cached)

    # 2) 없으면 LLM 실행
    inp = ArticleSummaryInput(
        article_id=article_id, 
        law_name=law_json["law_name"],
        title=art["title"],
        raw_text=art["raw_text"],
        domain=art["domain"],
    )

    result = chain.summary(inp)

    # 3) 결과 캐시에 저장
    save_cache(
        ctx,
        result.model_dump(),
        "article_summaries",
        f"{article_id}.json",
    )
    return result

def run_all_article_summaries(law_json, ctx):
    results = []

    chain = ArticleSummaryChain()  # ✅ 여기서 생성
    for ch in law_json["chapters"]:

        # 1) CHAPTER 직속 articles
        for art in ch.get("articles", []):
            results.append(process_article(art, ctx,law_json, chain))

        # 2) SECTION 직속 articles
        for sec in ch.get("sections", []):
            for art in sec.get("articles", []):
                results.append(process_article(art, ctx,law_json, chain))

            # 3) SUBDIVISION 직속 articles
            for sub in sec.get("subdivisions", []):
                for art in sub.get("articles", []):
                    results.append(process_article(art,ctx, law_json, chain))
        
    full_dump = [r.model_dump() for r in results]

    save_cache(
        ctx,
        full_dump,
        "article_summaries",
        "_ALL.json",
    )

    return results    


# ---------------------------
# ★ NormUnit - 1차 ★
# --------------------------- 
def process_norm_unit(article_id, domain, text,ctx, level, ref_dict, chain: NormUnitChain):
    # 캐시 파일명: article_id + level + ref 조합
    suffix = f"{level}_{ref_dict.get('para_no')}_{ref_dict.get('item_no')}_{ref_dict.get('subitem_no')}"
    suffix = suffix.replace("None", "X")
    fname = f"{article_id}__{suffix}.json"

    # 캐시 있으면 반환
    cached = load_cache(ctx, "norm_units", fname)
    if cached:
        return NormUnitOutput(**cached)

    # LLM 실행
    inp = NormUnitInput(
        article_id=article_id,
        text=text,
        level=level,
        domain=domain,
        ref=ref_dict
    )
    result = chain.tag(inp)

    # 캐시 저장
    save_cache(ctx, result.model_dump(), "norm_units", fname)
    return result


def extract_article_unit(art):
    return {
        "text": art["title"],
        "level": "ARTICLE",
        "ref": {"para_no": None, "item_no": None, "subitem_no": None}
    }

def extract_paragraph_units(art):
    paragraphs = art.get("paragraphs", [])
    units = []

    if not paragraphs:
        return units

    for p in paragraphs:
        units.append({
            "text": p["text"],
            "level": "PARAGRAPH",
            "ref": {
                "para_no": p.get("para_no"),
                "item_no": None,
                "subitem_no": None
            }
        })
    return units

def extract_item_units(art):
    units = []
    paragraphs = art.get("paragraphs", [])

    # CASE 1) 정상 구조: paragraph 아래 items
    for p in paragraphs:
        for h in p.get("items", []):
            units.append({
                "text": h["text"],
                "level": "ITEM",
                "ref": {
                    "para_no": p.get("para_no"),
                    "item_no": h.get("item_no"),
                    "subitem_no": None,
                }
            })

    # CASE 2) paragraph가 없는데 article 바로 아래 items가 있는 조문
    # (DRF가 종종 이렇게 내려줌)
    if not paragraphs:
        direct_items = art.get("items", [])
        for h in direct_items:
            units.append({
                "text": h["text"],
                "level": "ITEM",
                "ref": {
                    "para_no": None,
                    "item_no": h.get("item_no"),
                    "subitem_no": None
                }
            })

    return units

def extract_subitem_units(art):
    units = []
    paragraphs = art.get("paragraphs", [])

    # CASE 1) paragraph → item → subitem 구조
    for p in paragraphs:
        for h in p.get("items", []):
            for m in h.get("subitems", []):
                units.append({
                    "text": m["text"],
                    "level": "SUBITEM",
                    "ref": {
                        "para_no": p.get("para_no"),
                        "item_no": h.get("item_no"),
                        "subitem_no": m.get("subitem_no"),
                    }
                })

    # CASE 2) paragraph 없고 article → item → subitem 구조
    if not paragraphs:
        direct_items = art.get("items", [])
        for h in direct_items:
            for m in h.get("subitems", []):
                units.append({
                    "text": m["text"],
                    "level": "SUBITEM",
                    "ref": {
                        "para_no": None,
                        "item_no": h.get("item_no"),
                        "subitem_no": m.get("subitem_no"),
                    }
                })

    return units


def extract_units_for_article(art):
    units = []

    # ARTICLE-level
    units.append(extract_article_unit(art))

    # lower levels
    units.extend(extract_paragraph_units(art))
    units.extend(extract_item_units(art))
    units.extend(extract_subitem_units(art))

    return units


def run_article_norm_units(art, chain, ctx, law_json):
    article_id = art["id"]
    domain = art["domain"]

    units = extract_units_for_article(art)
    outputs = []

    for u in units:
        result = process_norm_unit(
            article_id=article_id,
            domain=domain,
            ctx=ctx,
            text=u["text"],
            level=u["level"],
            ref_dict=u["ref"],
            chain=chain
        )
        outputs.append(result)

    return outputs

# NormUnit - 1차  파이프라인
def run_all_norm_units(law_json, ctx, chain: NormUnitChain):
    results = []

    for ch in law_json["chapters"]:
        for art in ch.get("articles", []):
            results.extend(
                run_article_norm_units(
                    art,
                    chain,
                    ctx,
                    law_json
                )
            )

        for sec in ch.get("sections", []):
            for art in sec.get("articles", []):
                results.extend(
                    run_article_norm_units(
                        art,
                        chain,
                        ctx,
                        law_json
                    )
                )

            for sub in sec.get("subdivisions", []):
                for art in sub.get("articles", []):
                    results.extend(
                        run_article_norm_units(
                            art,
                            chain,
                            ctx,
                            law_json
                        )
                    )

    # ---------------------------
    # ✅ FULL DUMP (형태 유지)
    # ---------------------------
    json_ready = []
    for r in results:
        if hasattr(r, "model_dump"):
            json_ready.append(r.model_dump())
        else:
            json_ready.append(r)

    save_cache(
        ctx,
        json_ready,
        "norm_units",
        "_ALL.json",
    )

    return results

# ---------------------------
# ★ NormUnit-2차(Corss-ref) ★
# --------------------------- 

def process_cross_ref_unit(article_id, text,ctx, level, ref_dict, chain: NormUnitCrossRefChain):
    
    suffix = f"{level}_{ref_dict.get('para_no')}_{ref_dict.get('item_no')}_{ref_dict.get('subitem_no')}"
    suffix = suffix.replace("None", "X")
    fname = f"{article_id}__{suffix}.json"

    # 캐시 있으면 즉시 반환
    cached = load_cache(ctx, "cross_refs", fname)
    if cached:
        return NormUnitCrossRefOutput(**cached)

    # LLM 실행
    inp = NormUnitCrossRefInput(
        article_id=article_id,
        text=text,
        level=level,
        ref=ref_dict
    )

    out = chain.extract(inp)

    # 캐시 저장
    save_cache(ctx, out.model_dump(), "cross_refs", fname)
    return out

def run_article_cross_refs(art, chain, ctx):
    article_id = art["id"]
    units = extract_units_for_article(art)

    outputs = []

    for u in units:
        result = process_cross_ref_unit(
            article_id=article_id,
            ctx=ctx,
            text=u["text"],
            level=u["level"],
            ref_dict=u["ref"],
            chain=chain
        )
        outputs.append(result)

    return outputs

def run_all_cross_refs(law_json, ctx, chain: NormUnitCrossRefChain):
    results = []

    for ch in law_json["chapters"]:
        # CHAPTER 직속
        for art in ch.get("articles", []):
            results.extend(run_article_cross_refs(art, chain, ctx))

        for sec in ch.get("sections", []):
            for art in sec.get("articles", []):
                results.extend(run_article_cross_refs(art, chain, ctx))

            for sub in sec.get("subdivisions", []):
                for art in sub.get("articles", []):
                    results.extend(run_article_cross_refs(art, chain, ctx))

    # ---------------------------
    # ✅ FULL DUMP (구조 유지)
    # ---------------------------
    json_ready = []
    for r in results:
        if hasattr(r, "model_dump"):
            json_ready.append(r.model_dump())
        else:
            json_ready.append(r)

    save_cache(
        ctx,
        json_ready,
        "cross_refs",
        "_ALL.json",
    )

    return results

# ---------------------------
# ★ Chapter_semantic ★
# --------------------------- 

#chapter_text 추출
def extract_chapter_text(chapter: dict) -> str:
    """
    Chapter 전체의 조문 텍스트를 순서대로 하나의 문자열로 합친다.
    Section/Subdivision 유무와 관계없이 robust하게 작동한다.
    """

    lines = []

    # 1) chapter-level title
    if chapter.get("name"):
        lines.append(f"[CHAPTER] {chapter['name']}")

    # 2) chapter 직속 articles
    for art in chapter.get("articles", []):
        lines.append(format_article_for_semantics(art))

    # 3) sections
    for sec in chapter.get("sections", []):
        if sec.get("name"):
            lines.append(f"[SECTION] {sec['name']}")

        # section 직속 articles
        for art in sec.get("articles", []):
            lines.append(format_article_for_semantics(art))

        # subdivisions
        for sub in sec.get("subdivisions", []):
            if sub.get("name"):
                lines.append(f"[SUBDIVISION] {sub['name']}")

            for art in sub.get("articles", []):
                lines.append(format_article_for_semantics(art))

    # 최종 합치기
    return "\n\n".join(lines)


def format_article_for_semantics(art: dict) -> str:
    """
    LLM이 의미론을 뽑기 쉽게 아티클 단위 텍스트를 정제해서 표현.
    제목 + raw_text를 붙인다.
    """
    title = art.get("title", "")
    body = art.get("raw_text", "")

    return f"[ARTICLE] {title}\n{body.strip()}"


def chunk_text(text: str, max_chars=12000):
    """
    LLM context 방지를 위해 텍스트를 max_chars 단위로 나눈다.
    문단 단위로 최대한 끊는다.
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for p in paragraphs:
        if len(current) + len(p) + 2 > max_chars:
            chunks.append(current.strip())
            current = p + "\n\n"
        else:
            current += p + "\n\n"

    if current.strip():
        chunks.append(current.strip())

    return chunks

#run_chapter_semantics(law_json, chapter_id, chain) 구현
def run_chapter_semantics(law_json, ctx, chapter_id, chain: ChapterSemanticChain):

    # 1) 캐시 체크
    fname = f"{chapter_id}.json"
    cached = load_cache(ctx, "chapter_semantic", fname)
    if cached:
        return cached
    
    # 2) 캐시 없으면 계산
    chapter = next(ch for ch in law_json["chapters"] if ch["id"] == chapter_id)
    text = extract_chapter_text(chapter)

    chunks = chunk_text(text, max_chars=12000)

    partial_results = []

    for i, chunk in enumerate(chunks):
        inp = ChapterSemanticInput(
            chapter_id=chapter["id"],
            chapter_name=chapter["name"],
            domain=chapter.get("domain", ""),
            text=chunk
        )
        partial = chain.semantic(inp)
        partial_results.append(partial)
    
    # 3) merge
    final = merge_semantics(partial_results)
    final_dict = final.model_dump()

    # 4) 캐시 저장
    save_cache(ctx, final_dict, "chapter_semantic", fname)
    return final_dict


# 챕터 전체 파이프라인
def build_all_chapter_semantics(
    law_json,
    chain: ChapterSemanticChain,
    ctx,
):
    """
    1) chapter_semantics 개별 캐시 생성 (CH_x.json)
    2) 전체 합본 생성 (_ALL.json)
    """

    all_results = {}

    for ch in law_json["chapters"]:
        cid = ch["id"]

        result = run_chapter_semantics(
            law_json=law_json,
            ctx=ctx,
            chapter_id=cid,
            chain=chain,
        )

        # 🔒 방어: dict가 아니면 변환
        if hasattr(result, "model_dump"):
            result = result.model_dump()

        all_results[cid] = result

    # ---------------------------
    # ✅ 전체 합본 캐시 저장 (dict만 저장)
    # ---------------------------
    save_cache(
        ctx,
        all_results,
        "chapter_semantic",
        "_ALL.json",
    )

    return all_results


def merge_semantics(results):
    final = results[0]

    issue_map = {}

    for r in results:
        for issue in r.issues:
            key = issue.issue_title  # 제목이 동일하면 같은 issue로 간주

            if key not in issue_map:
                issue_map[key] = issue
            else:
                # merge lists
                issue_map[key].conditions += issue.conditions
                issue_map[key].effects += issue.effects
                issue_map[key].exceptions += issue.exceptions
                issue_map[key].methods += issue.methods
                issue_map[key].cross_refs += issue.cross_refs

    final.issues = list(issue_map.values())
    return final

import json

def pretty_print_chapter_semantics(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n===== CHAPTER: {data['chapter_id']} / {data['chapter_name']} =====\n")
    print("### Chapter Summary\n")
    print(data.get("chapter_summary", ""))
    print("\n\n")

    for issue in data.get("issues", []):
        print(f"----- {issue['issue_id']} :: {issue['issue_title']} -----\n")

        print("● Issue Summary")
        print(issue.get("issue_summary", ""), "\n")

        print("● Conditions")
        for c in issue.get("conditions", []):
            print(f"  - {c}")
        print()

        print("● Effects")
        for e in issue.get("effects", []):
            print(f"  - {e}")
        print()

        print("● Exceptions")
        for ex in issue.get("exceptions", []):
            print(f"  - {ex}")
        print()

        print("● Methods")
        for m in issue.get("methods", []):
            print(f"  - {m}")
        print()

        print("● Cross References")
        for cr in issue.get("cross_refs", []):
            print(f"  - [{cr['type']}] {cr['target']} :: {cr['note']}")
        print("\n")

    print("===== END OF CHAPTER =====\n")


# ---------------------------
# ★ Chapter_reasoning ★
# --------------------------- 

def run_chapter_reasoning(law_json, ctx, chapter_id: str, chain: ChapterReasoningChain):
    fname = f"{chapter_id}.json"
    cached = load_cache(ctx, "chapter_reasoning", fname)
    if cached:
        return cached
    
    # 캐시가 없으면 계산
    chapter = next(ch for ch in law_json["chapters"] if ch["id"] == chapter_id)
    raw_text = extract_chapter_text(chapter)

    inp = ChapterReasoningInput(
        chapter_id=chapter["id"],
        chapter_name=chapter["name"],
        text=raw_text,
    )

    result = chain.run(inp)  # ChapterReasoningOutput
    final = result.model_dump()

    # (중요) Pydantic 검증 (파싱 실패 방지)
    final = ChapterReasoningOutput(**final).model_dump()

    # 캐시 저장
    save_cache(ctx, final, "chapter_reasoning", fname)
    return final
