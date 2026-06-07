# stage6_narrative.py

from bravo.input_builder import build_bravo_global_chunks
from bravo.chain import BravoNarrativeChain
from bravo.pipeline import run_narrative

def step_narrative(blocks, case_id):
    from utils.cache import save_cache, load_cache

    cached = load_cache(case_id, "narrative.json")
    if cached:
        return cached

    chunks = build_bravo_global_chunks(blocks)
    chain = BravoNarrativeChain()
    narrative = run_narrative(chunks, chain)

    save_cache(case_id, "narrative.json", narrative.model_dump())
    return narrative.model_dump()
