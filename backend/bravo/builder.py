#bravo/ir.py
from bravo.models_bravo import BravoNarrativeOutput

def print_bravo_blocks_after_merge(case_dict):
    """
    브라보 merge 이후 case_dict 상태에서
    bravo node + block을 다시 빌드해서
    사람이 읽을 수 있게 디버그 출력한다.
    """

    nodes = build_bravo_nodes(case_dict)
    blocks = build_bravo_blocks(nodes)

    for b in blocks:
        print(f"\n===== BLOCK {b['block_id']} =====")

        for n in b["nodes"]:
            print(
                f"[{n.pid}|{n.sid}] "
                f"{n.type2} / {n.role} / {n.reasoning_function} "
                f":: {n.text[:300]}"
            )


def build_pass0_narrative_chunks(narrative: BravoNarrativeOutput) -> list[dict]:
    """
    narrative 객체를 의미 단위 4~5개 청크로 분리하여 PASS0에 전달하기 위한 리스트를 구성한다.

    각 청크는 반드시 작은 JSON(dict) 형태로 구성한다.
    """

    chunks = []

    # 1) fact_summary + core_conflicts 묶음 (쟁점 연결성 높음)
    chunks.append({
        "fact_summary": narrative.fact_summary,
        "core_conflicts": narrative.core_conflicts,
    })

    # 2) 원고 주장
    chunks.append({
        "plaintiff_arguments": narrative.plaintiff_arguments
    })

    # 3) 피고 주장
    chunks.append({
        "defendant_arguments": narrative.defendant_arguments
    })

    # 4) 법리
    chunks.append({
        "legal_context": narrative.legal_context
    })

    # 5) 법원 판단
    chunks.append({
        "court_reasoning": narrative.court_reasoning
    })

    return chunks



def _infer_block(type2: str, role: str) -> str:
    # 문단 레벨이 우선
    if type2 in {"meta", "fact"}:
        return "fact"
    if type2 == "argument_plaintiff":
        return "argument_plaintiff"
    if type2 == "argument_defendant":
        return "argument_defendant"
    if type2 in {"legal_basis", "statute"}:
        return "legal_basis"
    if type2 == "reasoning_core":
        return "reasoning"

    # 혹시 이상한 애들 들어오면 fallback
    if role in {"conclusion"}:
        return "outcome"

    return "other"


def _infer_speaker(type2: str, role: str) -> str | None:
    # 기본: 문단 기준
    if type2 == "argument_plaintiff":
        return "plaintiff"
    if type2 == "argument_defendant":
        return "defendant"

    # reasoning / legal_basis는 기본적으로 법원 목소리
    if type2 in {"reasoning_core", "legal_basis", "statute"}:
        return "court"

    # role이 대놓고 주장인 경우
    if role == "argument_plaintiff":
        return "plaintiff"
    if role == "argument_defendant":
        return "defendant"
    if role in {"court_reasoning", "conclusion"}:
        return "court"

    return None



from pydantic import BaseModel
from typing import Optional, Literal


class BravoNode(BaseModel):
    pid: int                  # paragraph index
    sid: str                  # sentence id ("5-2")
    text: str                 # raw sentence text

    # LAYER: semantic info from refine_para + attach_sent
    type2: str                # fact / argument_plaintiff / argument_defendant / legal_basis / reasoning_core / statute
    role: str                 # fact_recall / argument_plaintiff / court_reasoning 등

    # LAYER: logic-friendly flags (브라보 전용)
    speaker: Optional[str] = None   # plaintiff / defendant / court
    is_argument: bool
    is_court_reasoning: bool
    is_reasoning_core: bool
    is_legal_basis: bool
    is_fact: bool

    # LAYER: PASS1/PASS2에서 추가될 값
    reasoning_issue: Optional[str] = None
    reasoning_function: Optional[str] = None
    
    def to_dict(self):
        return self.model_dump()

END_TRIGGERS = [
    "주문과 같이",
    "주문과 같 다",
    "판결한다",
    "판결한 ",
    "인용하기로",
    "기각하기로",
    "인용한 ",
    "기각한 ",
    "재판장 판사",
    "판사 ",
]

def sentence_has_end_trigger(text):
    if not text:
        return False
    return any(t in text for t in END_TRIGGERS)


def build_bravo_blocks(nodes):
    """
    BravoNode 리스트를 받아 reasoning block으로 묶는다.
    reasoning_core(type2) 또는 COURT_REASONING(role)에서 block 시작
    block 시작 전 fact/argument/legal_basis는 PREAMBLE로 포함
    end-trigger 만나면 block 종료
    """
    blocks = []
    current_block = None
    block_id = 1

    # preamble 버퍼: reasoning 시작 전 fact/argument를 모아두었다가 함께 넣기
    preamble: List[BravoNode] = []

    for n in nodes:
        t2 = n.type2
        role = n.role
        text = n.text

        # --- 1) block 시작 조건 ---
        is_reasoning_start = (t2 == "reasoning_core") or (role == "COURT_REASONING")

        if is_reasoning_start:
            # 이전 블록 종료
            if current_block is not None:
                blocks.append(current_block)

            current_block = {
                "block_id": block_id,
                "nodes": [],
                "has_conclusion": False,
            }
            block_id += 1

            # preamble first
            # 🔥 첫 reasoning 블록 시작 시, preamble을 한 번에 밀어넣기
            if preamble:
                current_block["nodes"].extend(preamble)
                preamble = []

        # --- 0) preamble 수집 (reasoning 시작 전) ---
        if current_block is None:
            # reasoning 시작 전의 fact/argument/legal_basis만 버퍼에 모음
            if t2 == "fact" or t2 == "argument" or t2 == "legal_basis":
                preamble.append(n)
            continue


        # -----------------------------------------
        # 1) block 내부 처리
        # -----------------------------------------
        # end-trigger 감지        

        if sentence_has_end_trigger(text):
            current_block["nodes"].append(n)
            current_block["has_conclusion"] = True
            blocks.append(current_block)
            current_block = None
            preamble = []
            continue

        # --- 3) 기본 삽입 ---
        current_block["nodes"].append(n)

        # 소결론 감지
        if role == "CONCLUSION":
            current_block["has_conclusion"] = True

    # -----------------------------------------
    # 마지막 block 정리
    # -----------------------------------------
    if current_block is not None:
        blocks.append(current_block)

    return blocks




from typing import List

SAFE_TYPES = {"meta", "fact", "outcome"}


def build_bravo_nodes(case_dict: dict) -> List[BravoNode]:
    """
    sentence role까지 붙은 case_dict를 받아서
    한 줄당 하나의 논리 노드 리스트로 flatten.
    """
    nodes: List[BravoNode] = []

    paragraphs = case_dict.get("paragraphs", [])

    for p in paragraphs:
        # 🔥 appendix 문단은 통째로 제외
        if p.get("is_appendix"):
            continue
        
        pid = p["idx"]
        type2 = p["type2"]
        for s in p.get("sentences", []):
            text = s["sentence"].strip()
            if not text:
                continue

            role = s.get("role")
            sid = s.get("sid")

            if not role:
                role = "meta_info" if type2 in SAFE_TYPES else "unknown"


            block = _infer_block(type2, role)
            speaker = _infer_speaker(type2, role)

            # --- logic flags ---
            is_argument = (type2 == "argument_plaintiff") or (type2 == "argument_defendant")or(role in {"ARGUMENT_PLAINTIFF", "ARGUMENT_DEFENDANT"})
            is_court_reasoning = (role == "COURT_REASONING")
            is_reasoning_core = (type2 == "reasoning_core")
            is_legal_basis = (type2 == "legal_basis") or (role == "LEGAL_BASIS")
            is_fact = (type2 == "fact")

            node = BravoNode(
                pid=pid,
                sid=sid,
                text=text,
                type2=type2,
                block=block,
                role=role,
                speaker=speaker,
                is_argument=is_argument,
                is_court_reasoning=is_court_reasoning,
                is_reasoning_core=is_reasoning_core,
                is_legal_basis=is_legal_basis,
                is_fact=is_fact,
            )
            nodes.append(node)

    return nodes

def bravo_node_to_dict(node):
    """
    BravoNode -> dict
    prime의 node_to_dict와는 완전히 다름.
    Bravo 레이어에서 필요한 정보만 넣는다.
    """

    return {
        "pid": node.pid,
        "sid": node.sid,
        "text": node.text,

        # semantic info
        "type2": node.type2,
        "role": node.role,
        "speaker": node.speaker,

        # logic flags
        "is_argument": node.is_argument,
        "is_court_reasoning": node.is_court_reasoning,
        "is_reasoning_core": node.is_reasoning_core,
        "is_legal_basis": node.is_legal_basis,
        "is_fact": node.is_fact,

        # PASS1 / PASS2 결과 (초기에는 None)
        "reasoning_issue": node.reasoning_issue,
        "reasoning_function": node.reasoning_function,
    }

def bravo_block_to_dict(block):
    return {
        "block_id": block["block_id"],
        "has_conclusion": block["has_conclusion"],
        "nodes": [bravo_node_to_dict(n) for n in block["nodes"]]
    }


def build_pass2_nodes(case_dict: dict) -> List[BravoNode]:
    nodes = []

    paragraphs = case_dict.get("paragraphs", [])

    for p in paragraphs:
        if p.get("is_appendix"):
            continue

        pid = p["idx"]
        type2 = p["type2"]

        for s in p.get("sentences", []):
            text = s["sentence"].strip()
            if not text:
                continue

            role = s.get("role")
            sid = s.get("sid")

            # --- 🔥 FACT / META 제거 ---
            if type2 in {"meta", "fact"}:
                continue
            if role in {"META_INFO", "FACT_RECALL"}:
                continue

            # --- remaining types: argument / court_reasoning / legal_basis / reasoning_core
            is_argument = (type2.startswith("argument"))
            is_court_reasoning = (role == "COURT_REASONING")
            is_reasoning_core = (type2 == "reasoning_core")
            is_legal_basis = (type2 == "legal_basis")

            node = BravoNode(
                pid=pid,
                sid=sid,
                text=text,
                type2=type2,
                role=role,
                speaker=_infer_speaker(type2, role),
                is_argument=is_argument,
                is_court_reasoning=is_court_reasoning,
                is_reasoning_core=is_reasoning_core,
                is_legal_basis=is_legal_basis,
                is_fact=False,
            )
            nodes.append(node)

    return nodes

def build_pass2_blocks(nodes):
    blocks = []
    current_block = None
    block_id = 1

    for n in nodes:
        t2 = n.type2
        role = n.role
        text = n.text

        # --- 🔥 reasoning section에서만 block 시작 ---
        is_reasoning_start = (
            t2 == "reasoning_core" 
            or role == "COURT_REASONING"
            or t2 == "legal_basis"
            or t2.startswith("argument")
        )

        if is_reasoning_start:
            # close existing block
            if current_block is not None:
                blocks.append(current_block)

            current_block = {
                "block_id": block_id,
                "nodes": [],
            }
            block_id += 1

        # still no block started? skip
        if current_block is None:
            continue

        # append node
        current_block["nodes"].append(n)

        # optional: detect block end
        if sentence_has_end_trigger(text):
            blocks.append(current_block)
            current_block = None

    if current_block:
        blocks.append(current_block)

    return blocks
