# stage1_structure_raw.py

from paragraph.chain import CaseChainFactory
from paragraph.case_structure import build_case_structure

def step_structure_raw(cleaned, raw, case_id: str):
    from utils.cache import save_cache, load_cache

    cached = load_cache(case_id, "structure_raw.json")
    if cached:
        return cached

    factory = CaseChainFactory()

    structured = build_case_structure(
        case_id=case_id,
        cleaned_text=cleaned,
        raw_text=raw,
        factory=factory
    )

    save_cache(case_id, "structure_raw.json", structured.model_dump())
    save_cache(case_id, "metadata.json", structured.metadata.model_dump())
    # statutes → list[Pydantic] → list[dict]
    save_cache(case_id, "statutes.json", [s.model_dump() for s in structured.statutes])

    return structured.model_dump()
