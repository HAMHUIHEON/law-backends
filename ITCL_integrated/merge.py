import json
import os

"""
Integrated full pipeline 마지막에
merge_reasoning_with_alignment(
    prefix="ITCL_integrated",
    set_key=set_key,
)
"""
def integrated_cache_paths(*, prefix: str, set_key: str) -> dict:
    base = os.path.join("cache", prefix, set_key)

    return {
        "base": base,
        "semantic_dict": os.path.join(base, "02_semantic_dict.json"),
        "reasoning_dict": os.path.join(base, "03_reasoning_dict.json"),
        "alignment": os.path.join(base, "04_chapter_sr_align.json"),
        "reasoning_enriched": os.path.join(base, "05_reasoning_enriched.json"),
    }

import json
import os


def merge_reasoning_with_alignment(
    *,
    prefix: str,
    set_key: str,
):
    paths = integrated_cache_paths(prefix=prefix, set_key=set_key)

    reasoning_path = paths["reasoning_dict"]
    alignment_path = paths["alignment"]
    out_path = paths["reasoning_enriched"]

    if not os.path.exists(reasoning_path):
        raise FileNotFoundError(reasoning_path)

    if not os.path.exists(alignment_path):
        raise FileNotFoundError(alignment_path)

    with open(reasoning_path, "r", encoding="utf-8") as f:
        reasoning = json.load(f)

    with open(alignment_path, "r", encoding="utf-8") as f:
        alignment = json.load(f)

    for chapter_id, align_block in alignment.items():
        if chapter_id not in reasoning:
            continue

        reasoning_issues = reasoning[chapter_id].get("reasoning", [])

        for item in align_block.get("alignments", []):
            idx = item["reasoning_issue_index"] - 1  # 1-based → 0-based

            if 0 <= idx < len(reasoning_issues):
                reasoning_issues[idx]["semantic_issue_id"] = item.get("semantic_issue_id")
                reasoning_issues[idx]["alignment_confidence"] = item.get("confidence")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(reasoning, f, ensure_ascii=False, indent=2)

    print(f"✅ reasoning + alignment merge 완료 ({set_key})")

    return reasoning


