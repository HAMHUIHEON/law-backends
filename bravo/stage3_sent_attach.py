# stage3_sent_attach.py

from refine_para.post_rule import refine_postprocess
from attach_sent.attach_sentence import attach_sentences
from attach_sent.sentence_splitter import split_sentences

def step_sent_attach(structure_type2, case_id: str):
    from utils.cache import save_cache, load_cache

    cached = load_cache(case_id, "case_sentences.json")
    if cached:
        return cached

    case_data = structure_type2

    for p in case_data["paragraphs"]:
        if p["type2"] == "reasoning_core":
            corrected = refine_postprocess(p.get("summary") or p["text"], p["type2"])
            p["type2"] = corrected

    case_sent = attach_sentences(case_data, split_sentences)

    save_cache(case_id, "case_sentences.json", case_sent)
    return case_sent
