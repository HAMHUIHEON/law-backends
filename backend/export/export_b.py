# export/export_b.py

from utils.cache import load_cache

def build_export_B(case_id: str):
    meta = load_cache(case_id, "metadata.json")
    narrative = load_cache(case_id, "narrative.json")
    issue_frame = load_cache(case_id, "issue_frame.json")
    statutes =load_cache(case_id, "statutes.json")
    
    return {
        "metadata": meta,
        "narrative": narrative,
        "issue_frame": issue_frame,
        "statutes" : statutes
    }
