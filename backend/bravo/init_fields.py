#prime/start_porint.py

"""
Bravo → 논증 구조 (Logical Structure)

attach_sent이후 딕트 가지고 와서 진입 초기상태 만들기
case_dict["paragraphs"][pid]["sentences"][sid] = {
    "sentence": "...",
    "role": "...",
    "type2": "...",
    "reasoning_function": None  # placeholder
}
"""


def init_bravo_fields(case_dict):
    for p in case_dict["paragraphs"]:
        for s in p.get("sentences", []):
            s["reasoning_function"] = None
    return case_dict


"""
case_dict (sentence role까지 끝난 상태)
 → [init_bravo_fields] reasoning_function = None 초기화
 → nodes = build_prime_nodes(...)
 → blocks = build_prime_blocks(nodes)
 → bravo_inputs = build_bravo_inputs(blocks)
 → LLM chain 호출
 → apply_bravo_functions(blocks, outputs)
 → merge_bravo_to_case(case_dict, blocks)
"""
