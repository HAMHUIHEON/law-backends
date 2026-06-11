# stage5_bravo_tree.py

from bravo.init_fields import init_bravo_fields
from bravo.builder import build_bravo_nodes, build_bravo_blocks

def step_bravo_tree(case_sentence_final, case_id):
    from utils.cache import save_cache, load_cache

    cached_nodes = load_cache(case_id, "bravo_nodes.json")
    cached_blocks = load_cache(case_id, "bravo_blocks.json")
    if cached_nodes and cached_blocks:
        return cached_nodes, cached_blocks

    case_bravo = init_bravo_fields(case_sentence_final)
    nodes = build_bravo_nodes(case_bravo)
    blocks = build_bravo_blocks(nodes)

    save_cache(case_id, "bravo_nodes.json", [n.to_dict() for n in nodes])
    save_cache(case_id, "bravo_blocks.json", exportable_blocks(blocks))

    return nodes, blocks

def exportable_blocks(blocks):
    export_list = []
    for b in blocks:
        export_list.append({
            "block_id": b["block_id"],
            "has_conclusion": b.get("has_conclusion"),
            "nodes": [n.to_dict() for n in b["nodes"]],
        })
    return export_list
