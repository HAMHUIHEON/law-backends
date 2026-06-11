# stage9_issue_logic.py

from bravo.input_builder import build_bravo_global_chunks
from bravo.chain import BravoGlobalChain
from bravo.pipeline import run_global_outline

def step_issue_logic(blocks, case_id):
    from utils.cache import save_cache, load_cache

    cached = load_cache(case_id, "issue_logic.json")
    if cached:
        return cached

    chunks = build_bravo_global_chunks(blocks)
    chain = BravoGlobalChain()
    outline = run_global_outline(chunks, chain)

    save_cache(case_id, "issue_logic.json", outline.model_dump())
    return outline.model_dump()
