# stage8_issue_frame.py

from bravo.input_builder import build_bravo_global_chunks
from bravo.chain import ReasoningIssueChain
from bravo.pipeline import merge_issue_outputs
from bravo.models_bravo import BravoIssueInput

def step_issue_frame(blocks, cluster_json, case_id):
    from utils.cache import save_cache, load_cache

    cached = load_cache(case_id, "issue_frame.json")
    if cached:
        return cached

    representative_keywords = list(cluster_json["clusters"].keys())

    chunks = build_bravo_global_chunks(blocks)
    issue_chain = ReasoningIssueChain()

    partials = []
    for ch in chunks:
        inp = BravoIssueInput(full_text=ch, keywords=representative_keywords)
        partials.append(issue_chain.extract(inp))

    issue_frame = merge_issue_outputs(partials)

    save_cache(case_id, "issue_frame.json", issue_frame.model_dump())
    return issue_frame.model_dump()
