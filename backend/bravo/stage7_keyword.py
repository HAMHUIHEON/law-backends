# stage7_keyword.py

from concurrent.futures import ThreadPoolExecutor
from bravo.chain import BravoKeywordChain, BravoSignatureChain
from bravo.utils import build_signature_map
from bravo.pipeline import run_cluster_issue_keywords

def step_keywords(narrative, case_id):
    from utils.cache import save_cache, load_cache

    cached_map = load_cache(case_id, "keyword_map.json")
    cached_sig = load_cache(case_id, "keyword_signature.json")
    cached_clu = load_cache(case_id, "keyword_cluster.json")

    if cached_map and cached_sig and cached_clu:
        return cached_map, cached_sig, cached_clu

    core_conflicts = narrative["core_conflicts"]

    keyword_chain = BravoKeywordChain()

    def _extract_kw(c):
        return c, keyword_chain.extract(c).keywords

    with ThreadPoolExecutor(max_workers=5) as exe:
        keyword_map = dict(exe.map(_extract_kw, core_conflicts))

    signature_data = build_signature_map(keyword_map)

    sig_chain = BravoSignatureChain()
    cluster_obj = run_cluster_issue_keywords(keyword_map, sig_chain)

    save_cache(case_id, "keyword_map.json", keyword_map)
    save_cache(case_id, "keyword_signature.json", signature_data)
    save_cache(case_id, "keyword_cluster.json", cluster_obj.model_dump())

    return keyword_map, signature_data, cluster_obj.model_dump()
