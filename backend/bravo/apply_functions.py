# bravo/apply_functions.py
"block-level function → nodes → case_dict"

def apply_bravo_functions(blocks, outputs):
    """
    blocks: list of reasoning blocks
    outputs: list[BravoBlockOutput]  (reasoning_function만 있음)
    """
    for block, out in zip(blocks, outputs):
        funcs = out.reasoning_function or []
        nodes = block["nodes"]

        for node, func in zip(nodes, funcs):
            node.reasoning_function = func

    return blocks

