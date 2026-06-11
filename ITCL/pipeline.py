# ITCL/pipeline_law.py

import json
import os
from pathlib import Path

# --- converters ---
from ITCL.convert_drf_law_to_unified import convert_drf_law_to_unified

# --- domain ---
from ITCL.domain_assign import load_domain_map_for_snapshot,apply_domain_map,assign_domains,build_normalized_domain_lookup

# --- chain layer ---
from ITCL.run import (
    run_all_article_summaries,
    run_all_norm_units,
    run_all_cross_refs,
    build_all_chapter_semantics,
    run_chapter_semantics,
    run_chapter_reasoning,
)

from ITCL.chain import (
    ArticleSummaryChain,
    NormUnitChain,
    NormUnitCrossRefChain,
    ChapterSemanticChain,
    ChapterReasoningChain,
)

# --- merge + ingest ---
from ITCL.merge import merge_into_converted, attach_article_summaries
from ITCL.ingest_norm_itcl import run_ingest_norm
from ITCL.ingest_logic_itcl import run_ingest_logic

from concurrent.futures import ThreadPoolExecutor

# --------------------------------------------------
# 유틸
# --------------------------------------------------

def load_drf_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
    
    
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


def save_cache_with_context(ctx, obj, filename):
    path = os.path.join(ctx["base_dir"], filename)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# --------------------------------------------------
# STEP 0: unify
# --------------------------------------------------

def step_unify(
    raw_json,
    *,
    snapshot: dict,
    law_drf_path: str,
):
    law = convert_drf_law_to_unified(raw_json)
    ctx = make_version_context(law)

    # 🔥 여기서 세트별 domain 적용
    domain_map = load_domain_map_for_snapshot(
        snapshot=snapshot,
        law_drf_path=law_drf_path,
    )

    domain_lookup = build_normalized_domain_lookup(domain_map)  # ✅ 추가
    apply_domain_map(law, domain_lookup)
    assign_domains(law)

    save_cache_with_context(ctx, law, "00_unified.json")
    return ctx, law


# --------------------------------------------------
# STEP 1: norm layer
# --------------------------------------------------

def step_norm(ctx, law):
    n_chain = NormUnitChain()
    c_chain = NormUnitCrossRefChain()

    summaries = run_all_article_summaries(law, ctx)
    norm_units = run_all_norm_units(law, ctx, n_chain)
    cross_refs = run_all_cross_refs(law, ctx, c_chain)

    merged1 = merge_into_converted(law, norm_units, cross_refs)
    merged1 = attach_article_summaries(merged1, summaries)

    save_cache_with_context(ctx, merged1, "01_norm_enriched.json")
    return merged1

def step_norm_parallel(ctx, law):
    n_chain = NormUnitChain()
    c_chain = NormUnitCrossRefChain()

    with ThreadPoolExecutor(max_workers=3) as ex:
        f_summary = ex.submit(run_all_article_summaries, law, ctx)
        f_norm    = ex.submit(run_all_norm_units, law, ctx, n_chain)
        f_cross   = ex.submit(run_all_cross_refs, law, ctx, c_chain)

        summaries  = f_summary.result()
        norm_units = f_norm.result()
        cross_refs = f_cross.result()

    merged = merge_into_converted(law, norm_units, cross_refs)
    merged = attach_article_summaries(merged, summaries)

    save_cache_with_context(ctx, merged, "01_norm_enriched.json")
    return merged

# --------------------------------------------------
# STEP 2: chapter semantic
# --------------------------------------------------

def step_chapter_semantics(ctx, law):
    sem_chain = ChapterSemanticChain()
    sem_dict = build_all_chapter_semantics(law, sem_chain, ctx)

    save_cache_with_context(ctx, sem_dict, "02_semantic_dict.json")
    return sem_dict

# --------------------------------------------------
# STEP 3: chapter reasoning
# --------------------------------------------------

def step_chapter_reasoning(ctx, law):
    rea_chain = ChapterReasoningChain()
    results = {}

    for ch in law["chapters"]:
        cid = ch["id"]
        results[cid] = run_chapter_reasoning(
        law_json=law,
        ctx=ctx,
        chapter_id=cid,
        chain=rea_chain,
    )


    save_cache_with_context(ctx, results, "03_reasoning_dict.json")
    return results


# --------------------------------------------------
# STEP 4: merge semantic + reasoning → final JSON
# --------------------------------------------------

def step_merge_logic(ctx, base_law, semantic_dict, reasoning_dict):
    for ch in base_law["chapters"]:
        cid = ch["id"]
        ch["chapter_semantic"] = []
        ch["chapter_reasoning"] = []

        if cid in semantic_dict:
            ch["chapter_semantic"].append(semantic_dict[cid])

        if cid in reasoning_dict:
            ch["chapter_reasoning"].append(reasoning_dict[cid])

    save_cache_with_context(ctx, base_law, "04_logic_enriched.json")
    return base_law


# --------------------------------------------------
# STEP 2+3+4: chapter semantics & reasoning & merge- parallel
# --------------------------------------------------
# 1) 동시
def run_chapter_semantic_and_reasoning(law, ctx, ch, sem_chain, rea_chain):
    cid = ch["id"]

    sem = run_chapter_semantics(
        law_json=law,
        ctx=ctx,
        chapter_id=cid,
        chain=sem_chain,
    )
    rea = run_chapter_reasoning(
        law_json=law,
        ctx=ctx,
        chapter_id=cid,
        chain=rea_chain,
    )

    return cid, sem, rea

# 2) 병렬 움직이기
def step_chapter_logic_parallel(ctx, law):
    sem_chain = ChapterSemanticChain()
    rea_chain = ChapterReasoningChain()

    semantic_dict = {}
    reasoning_dict = {}

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = [
            ex.submit(
                run_chapter_semantic_and_reasoning,
                law,
                ctx,
                ch,
                sem_chain,
                rea_chain
            )
            for ch in law["chapters"]
        ]
        for f in futures:
            cid, sem, rea = f.result()
            semantic_dict[cid] = sem
            reasoning_dict[cid] = rea

    save_cache_with_context(ctx, semantic_dict, "02_semantic_dict.json")
    save_cache_with_context(ctx, reasoning_dict, "03_reasoning_dict.json")

    merged = step_merge_logic(ctx, law, semantic_dict, reasoning_dict)
    return merged



# --------------------------------------------------
# STEP 5: ingest
# --------------------------------------------------

def step_ingest(final_law):
    run_ingest_norm(final_law)
    run_ingest_logic(final_law)
    return True


# --------------------------------------------------
# STEP 6: full pipeline
# --------------------------------------------------

def run_law_pipeline(
    drf_json_path: str,
    *,
    snapshot: dict,
    law_drf_path: str,
):
    raw = load_drf_json(drf_json_path)

    ctx, unified = step_unify(
        raw,
        snapshot=snapshot,
        law_drf_path=law_drf_path,
    )

    normed = step_norm_parallel(ctx, unified)
    final = step_chapter_logic_parallel(ctx, normed)

    step_ingest(final)
    return final

