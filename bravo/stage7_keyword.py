# stage7_keyword.py
# LLM 없이 core_conflicts를 그대로 cluster 키로 사용.
# BravoKeywordChain + BravoSignatureChain 제거 — LLM 4~6회 절감/케이스.

def step_keywords(narrative, case_id):
    from utils.cache import save_cache, load_cache

    cached_map = load_cache(case_id, "keyword_map.json")
    cached_sig = load_cache(case_id, "keyword_signature.json")
    cached_clu = load_cache(case_id, "keyword_cluster.json")

    if cached_map and cached_sig and cached_clu:
        return cached_map, cached_sig, cached_clu

    core_conflicts = narrative.get("core_conflicts", [])

    # core_conflicts를 그대로 cluster 키로 사용 (LLM 호출 없음)
    keyword_map = {c: [c] for c in core_conflicts}
    signature_data = {c: [c] for c in core_conflicts}
    cluster_obj = {"clusters": {c: [] for c in core_conflicts}}

    save_cache(case_id, "keyword_map.json", keyword_map)
    save_cache(case_id, "keyword_signature.json", signature_data)
    save_cache(case_id, "keyword_cluster.json", cluster_obj)

    return keyword_map, signature_data, cluster_obj
