#ITCL_integrated/run.py

# ITCL_integrated/run.py

import os
import json
from typing import List, Dict
from ITCL_integrated.models import (IntegratedChapterSemanticInput,IntegratedChapterReasoningInput,
                                    IntegratedChapterReasoningOutput,IntegratedChapterSemanticOutput,
                                    ChapterAlignmentInput,ChapterAlignmentOutput)
from ITCL_integrated.chain import (IntegratedChapterReasoningChain,IntegratedChapterSemanticChain,
                                   IntegratedChapterAlignmentChain)

from concurrent.futures import ThreadPoolExecutor

"""
cache/
└─ ITCL_integrated/
   └─ LAW_20171219_15221__DECREE_20171219_15222__RULE_20171219_15223/
      ├─ chapter_semantic/
      │   ├─ CH_1.json
      │   └─ CH_2.json
      ├─ chapter_reasoning/
      │   ├─ CH_1.json
      │   └─ CH_2.json
      ├─ 02_semantic_dict.json
      ├─ 03_reasoning_dict.json
      ├─ 04_chapter_sr_align.json
      └─ 05_reasoning_enriched.json

"""


#=============
# 풀 파이프라인
#=============

def run_integrated_full_pipeline(
    *,
    law: dict,
    admrul: dict,
    rule: dict,
    prefix: str = "ITCL_integrated",
):
    """
    Integrated full pipeline

    1) LAW / DECREE / RULE 조합으로 set_key 생성
    2) Integrated Semantic + Reasoning 병렬 실행
    3) Semantic + Reasoning 결과로 Alignment 실행
    """

    # --------------------------------------------------
    # 0) set_key (Integrated 세트 식별자)
    # --------------------------------------------------
    set_key = integrated_set_key(law, admrul, rule)

    print(f"🚀 Integrated pipeline start")
    print(f"🔑 set_key = {set_key}")

    # --------------------------------------------------
    # 1) Chains 생성
    # --------------------------------------------------
    semantic_chain  = IntegratedChapterSemanticChain()
    reasoning_chain = IntegratedChapterReasoningChain()
    align_chain     = IntegratedChapterAlignmentChain()

    # --------------------------------------------------
    # 2) Semantic / Reasoning 병렬 실행
    # --------------------------------------------------
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_sem = ex.submit(
            run_all_integrated_chapter_semantics,
            law,
            admrul,
            rule,
            semantic_chain,
            prefix,
        )

        f_rea = ex.submit(
            run_all_integrated_chapter_reasoning,
            law,
            admrul,
            rule,
            reasoning_chain,
            prefix,
        )

        semantic_dict  = f_sem.result()
        reasoning_dict = f_rea.result()

    # --------------------------------------------------
    # 3) Alignment (순차 / 의존)
    # --------------------------------------------------
    alignment_dict = run_all_chapter_alignment(
        semantic_dict=semantic_dict,
        reasoning_dict=reasoning_dict,
        chain=align_chain,
        set_key=set_key,
        prefix=prefix,
    )

    print("✅ Integrated full pipeline completed")

    return {
        "set_key": set_key,
        "semantic": semantic_dict,
        "reasoning": reasoning_dict,
        "alignment": alignment_dict,
    }




def integrated_set_key(law: dict, admrul: dict, rule: dict) -> str:
    def k(x):
        m = x.get("metadata", {})
        return f"{m.get('공포일자','UNKNOWN')}_{m.get('공포번호','UNKNOWN')}"
    return f"LAW_{k(law)}__DECREE_{k(admrul)}__RULE_{k(rule)}"



# ---------------------------
# Chapter → Text
# ---------------------------
def extract_chapter_text(chapter: dict) -> str:
    """
    Chapter 전체의 조문 텍스트를 순서대로 하나의 문자열로 합친다.
    Section/Subdivision 유무와 관계없이 robust하게 작동한다.
    """

    lines: List[str] = []

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
    """
    title = art.get("title", "").strip()
    body = art.get("raw_text", "").strip()
    return f"[ARTICLE] {title}\n{body}"



# ---------------------------
# Integrated Chapter Text
# ---------------------------
def extract_integrated_chapter_text(
    law_json: dict,
    admrul_json: dict,
    rule_json: dict,
    chapter_id: str,
) -> str:
    blocks = []

    """
    동일 chapter_id 기준으로
    법 / 시행령 / 시행규칙 텍스트를 순서대로 통합한다.
    """
    blocks: List[str] = []

    def extract_from(source_name: str, law_obj: dict):
        ch = next((c for c in law_obj["chapters"] if c["id"] == chapter_id), None)
        if not ch:
            return

        blocks.append(f"\n===== [{source_name}] {ch['name']} =====\n")
        blocks.append(extract_chapter_text(ch))

    extract_from("LAW", law_json)
    extract_from("DECREE", admrul_json)
    extract_from("RULE", rule_json)

    return "\n\n".join(blocks)

# ---------------------------
# Chunking
# ---------------------------
def chunk_text(text: str, max_chars=12000):
    """
    LLM context 초과 방지를 위해 문단 단위로 chunk 분할.
    """
    paragraphs = text.split("\n\n")
    chunks: List[str] = []
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

# ---------------------------
# Semantic Merge
# ---------------------------

def _dedup(items: List) -> List:
    """순서 유지하며 중복 제거"""
    return list(dict.fromkeys(items))

def merge_semantics(results):
    """
    chunk 단위 semantic 결과를
    issue_title 기준으로 통합한다.
    """
    final = results[0]
    issue_map: Dict[str, any] = {}

    for r in results:
        for issue in r.issues:
            key = issue.issue_title  # 제목이 동일하면 같은 issue로 간주

            if key not in issue_map:
                issue_map[key] = issue
            else:
                base = issue_map[key]
                base.conditions  = _dedup(base.conditions  + issue.conditions)
                base.effects     = _dedup(base.effects     + issue.effects)
                base.exceptions  = _dedup(base.exceptions  + issue.exceptions)
                base.methods     = _dedup(base.methods     + issue.methods)
                base.cross_refs  = _dedup(base.cross_refs  + issue.cross_refs)

    final.issues = list(issue_map.values())
    return final

# ---------------------------
# Run Integrated Chapter Semantic
# ---------------------------
#챕터별
def run_integrated_chapter_semantics(
    law: dict,
    admrul: dict,
    rule: dict,
    chapter_id: str,
    chain,
    prefix: str = "ITCL_integrated",
):
    """
    통합 Chapter Semantic 실행 함수
    """

    # 1) chapter 메타 확보
    ch = next(c for c in law["chapters"] if c["id"] == chapter_id)

    # 2) 캐시 체크
    set_key = integrated_set_key(law, admrul, rule)

    cache_dir = f"cache/{prefix}/{set_key}/chapter_semantic"
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{chapter_id}.json")

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    text = extract_integrated_chapter_text(
        law, admrul, rule, chapter_id
    )

    chunks = chunk_text(text, max_chars=12000)

    partials = []
    for chunk in chunks:
        inp = IntegratedChapterSemanticInput(
            chapter_id=chapter_id,
            chapter_name=ch["name"],
            domain=ch.get("domain", ""),
            text=chunk,
        )
        partials.append(chain.semantic(inp))

    final = merge_semantics(partials)
    final_dict = final.model_dump()

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(final_dict, f, ensure_ascii=False, indent=2)

    return final_dict

# idx 다시 만들기
def reindex_issue_ids(semantic_dict: dict) -> dict:
    """
    chapter 단위로 issue_id를 ISSUE_1, ISSUE_2, ... 로 재부여한다.
    - issue 순서는 기존 리스트 순서를 그대로 유지
    - issue_title / 내용은 절대 건드리지 않음
    """

    for chapter_id, chapter_data in semantic_dict.items():
        issues = chapter_data.get("issues")
        if not issues:
            continue

        for idx, issue in enumerate(issues, start=1):
            issue["issue_id"] = f"ISSUE_{idx}"

    return semantic_dict

# ---------------------------
# full_pipeline
# ---------------------------

def run_all_integrated_chapter_semantics(
    law: dict,
    admrul: dict,
    rule: dict,
    chain,
    prefix: str = "ITCL_integrated",
):
    results = {}
    chapter_ids = [ch["id"] for ch in law.get("chapters", [])]

    for i, cid in enumerate(chapter_ids, start=1):
        print(f"[{i}/{len(chapter_ids)}] Integrated semantic: {cid}")

        out = run_integrated_chapter_semantics(
            law=law,
            admrul=admrul,
            rule=rule,
            chapter_id=cid,
            chain=chain,
            prefix=prefix,
        )
        results[cid] = out

    results = reindex_issue_ids(results)
    set_key = integrated_set_key(law, admrul, rule)

    out_path = f"cache/{prefix}/{set_key}/02_semantic_dict.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results




# ---------------------------
# 챕터별 리즈닝
# ---------------------------
def run_integrated_chapter_reasoning(
    law,
    admrul,
    rule,
    chapter_id: str,
    chain: IntegratedChapterReasoningChain,
    prefix: str = "ITCL_integrated",
):

    set_key = integrated_set_key(law, admrul, rule)

    CACHE_DIR = f"cache/{prefix}/{set_key}/chapter_reasoning"
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{chapter_id}.json")

    # 1) 캐시 조회
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # 2) chapter 메타
    chapter = next(ch for ch in law["chapters"] if ch["id"] == chapter_id)

    # 3) 통합 텍스트 생성
    raw_text = extract_integrated_chapter_text(
        law,
        admrul,
        rule,
        chapter_id
    )

    # 4) LLM 실행
    inp = IntegratedChapterReasoningInput(
        chapter_id=chapter["id"],
        chapter_name=chapter["name"],
        text=raw_text,
    )

    result = chain.run(inp)
    final = result.model_dump()

    # 5) Pydantic 재검증
    final = IntegratedChapterReasoningOutput(**final).model_dump()

    # 6) 캐시 저장
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    return final


# ---------------------------
# full_pipeline
# ---------------------------
def run_all_integrated_chapter_reasoning(
    law: dict,
    admrul: dict,
    rule: dict,
    chain: IntegratedChapterReasoningChain,
    prefix: str = "ITCL_integrated",
):
    results = {}
    chapter_ids = [ch["id"] for ch in law.get("chapters", [])]

    for i, cid in enumerate(chapter_ids, start=1):
        print(f"[{i}/{len(chapter_ids)}] Integrated reasoning: {cid}")

        out = run_integrated_chapter_reasoning(
            law=law,
            admrul=admrul,
            rule=rule,
            chapter_id=cid,
            chain=chain,
            prefix=prefix,
        )
        results[cid] = out

    set_key = integrated_set_key(law, admrul, rule)

    out_path = f"cache/{prefix}/{set_key}/03_reasoning_dict.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results


# ---------------------------
# align
# ---------------------------

def run_chapter_alignment(
    chapter_id: str,
    semantic_dict: dict,
    reasoning_dict: dict,
    chain: IntegratedChapterAlignmentChain,
):
    sem = semantic_dict[chapter_id]
    rea = reasoning_dict[chapter_id]

    semantic_issues = [
        {
            "issue_id": s["issue_id"],
            "issue_title": s["issue_title"],
            "issue_summary": s["issue_summary"],
        }
        for s in sem["issues"]
    ]

    reasoning_issues = [
        {
            "reasoning_issue_index": i + 1,   # 1-based
            "issue_title": r["issue_title"],
            "summary": r["summary"],
        }
        for i, r in enumerate(rea["reasoning"])
    ]

    inp = ChapterAlignmentInput(
        chapter_id=chapter_id,
        semantic_issues=semantic_issues,
        reasoning_issues=reasoning_issues,
    )

    return chain.align(inp)


def run_all_chapter_alignment(
    semantic_dict: dict,
    reasoning_dict: dict,
    chain: IntegratedChapterAlignmentChain,
    set_key: str,  
    prefix: str = "ITCL_integrated",
):
    
    results = {}

    # chapter_ids = list(semantic_dict.keys())
    chapter_ids = sorted(set(semantic_dict) & set(reasoning_dict))
    
    for i, cid in enumerate(chapter_ids, start=1):
        print(f"[{i}/{len(chapter_ids)}] s&r_align: {cid}")

        out = run_chapter_alignment(
            chapter_id=cid,
            semantic_dict=semantic_dict,
            reasoning_dict=reasoning_dict,
            chain=chain,
        )
        results[cid] = out.model_dump() if hasattr(out, "model_dump") else out

    out_path = f"cache/{prefix}/{set_key}/04_chapter_sr_align.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results



