# stage4_sentence_role.py

from attach_sent.merge import build_sentence_inputs, refine_sentences
from attach_sent.sentence_role_chain import SentenceRoleChain

def step_sentence_role(case_sentences, case_id):
    from utils.cache import save_cache, load_cache

    cached = load_cache(case_id, "sentence_role.json")
    if cached:
        return cached

    role_chain = SentenceRoleChain()
    case_final = refine_sentences(case_sentences, role_chain)

    save_cache(case_id, "sentence_role.json", case_final)
    return case_final
