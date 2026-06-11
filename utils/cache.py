import os, json

CACHE_ROOT = "cache"

def ensure_case_folder(case_id):
    path = os.path.join(CACHE_ROOT, case_id)
    os.makedirs(path, exist_ok=True)
    return path

def save_cache(case_id, filename, data):
    path = ensure_case_folder(case_id)
    fp = os.path.join(path, filename)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return fp

def load_cache(case_id, filename):
    fp = os.path.join(CACHE_ROOT, case_id, filename)
    if not os.path.exists(fp):
        return None
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)
