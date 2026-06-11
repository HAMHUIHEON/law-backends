# bravo/input_builder.py

# from bravo.models_bravo import BravoBlockInput
from typing import List

def build_pass2_blocks_text(blocks):
    """
    BRAVO blocks(list of dict) → 
    PASS2-A에서 사용할 block-level 텍스트(list[str])로 변환.
    """
    out = []

    for b in blocks:
        # b["nodes"] 안에는 BravoNode 객체들이 들어있음
        lines = []
        for n in b["nodes"]:
            # node가 객체일 수도 있고 dict일 수도 있으니 방어코드
            txt = getattr(n, "text", None) or n.get("text")
            if txt:
                lines.append(txt.strip())

        out.append("\n".join(lines))

    return out

def build_bravo_global_chunks(blocks, max_len: int = 4000) -> List[str]:
    """
    BravoBlock 기반으로 글로벌 요약용 텍스트 chunk를 만든다.
    - 각 block은 이미 preamble + reasoning 문장들이 포함된 논리 단위임.
    - block 단위로 텍스트를 구성하고, max_len 기준으로 나눈다.
    """

    # 1) block 단위 텍스트 수집
    block_texts: List[str] = []
    for b in blocks:
        txt = "\n".join(
            (getattr(n, "text", None) or (n.get("text") if isinstance(n, dict) else "")) or ""
            for n in b["nodes"]
        )
        if txt.strip():
            block_texts.append(txt.strip())

    # 2) 길이 기준으로 chunk 분할
    chunks: List[str] = []
    buf = ""

    for block_txt in block_texts:
        # +1은 개행
        if len(buf) + len(block_txt) + 1 <= max_len:
            buf += block_txt + "\n\n"
        else:
            if buf.strip():
                chunks.append(buf.strip())
            buf = block_txt + "\n\n"

    if buf.strip():
        chunks.append(buf.strip())

    return chunks

def build_bravo_local_inputs(blocks, global_summary):
    """
    blocks: build_prime_blocks(nodes) 결과물
    global_summary: Pass1 결과 (dict)
    """
    inputs = []

    for b in blocks:
        sentences = [
            (getattr(n, "text", None) or (n.get("text") if isinstance(n, dict) else "")) or ""
            for n in b["nodes"]
        ]
        full_block_text = "\n".join(sentences)

        inp = {
            "global_summary": global_summary.dict() if hasattr(global_summary, "dict") else global_summary,
            "block_text": full_block_text,
            "sentences": sentences
        }
        inputs.append((b["block_id"], inp))

    return inputs
