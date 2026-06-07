# export/export_a.py

from utils.cache import load_cache

def build_export_A(case_id: str):
    meta = load_cache(case_id, "metadata.json")
    narrative = load_cache(case_id, "narrative.json")

    return {
        "metadata": meta,
        "narrative": narrative
    }
