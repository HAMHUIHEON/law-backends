# stage2_refine_type2.py

from paragraph.model import CaseRawStructured
from refine_para.merge import refine_case
from refine_para.chain import RefineCaseChainFactory

def step_type2(structure_raw, case_id: str):
    from utils.cache import save_cache, load_cache

    cached = load_cache(case_id, "structure_type2.json")
    if cached:
        return cached

    case_raw = CaseRawStructured(**structure_raw)
    factory = RefineCaseChainFactory()

    structure_type2 = refine_case(case_raw, factory)

    save_cache(case_id, "structure_type2.json", structure_type2)
    return structure_type2
