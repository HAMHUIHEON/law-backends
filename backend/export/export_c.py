# export/export_c.py

from utils.cache import load_cache

def build_export_C(case_id: str):
    meta = load_cache(case_id, "metadata.json")
    narrative = load_cache(case_id, "narrative.json")
    issue_logic = load_cache(case_id, "issue_logic.json")
    statutes =load_cache(case_id, "statutes.json")

    return {
        "metadata": meta,
        "narrative": narrative,
        "issue_logic": issue_logic,
        "statutes" : statutes
    }
