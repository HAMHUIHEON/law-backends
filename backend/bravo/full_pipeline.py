# bravo/full_pipeline.py

from bravo.stage0_raw import step_raw_and_paragraphs
from bravo.stage1_structure_raw import step_structure_raw
from bravo.stage2_refine_type2 import step_type2
from bravo.stage3_sent_attach import step_sent_attach
from bravo.stage4_sentence_role import step_sentence_role
from bravo.stage5_bravo_tree import step_bravo_tree
from bravo.stage6_narrative import step_narrative
from bravo.stage7_keyword import step_keywords
from bravo.stage8_issue_frame import step_issue_frame
from bravo.stage9_issue_logic import step_issue_logic
from bravo.stage10_citation import step_issue_citations
from pathlib import Path

def run_full_pipeline(pdf_path: str):

    case_id = Path(pdf_path).stem

    step0 = step_raw_and_paragraphs(pdf_path, case_id)
    structure_raw = step_structure_raw(step0["cleaned"], step0["raw"], case_id)
    structure_type2 = step_type2(structure_raw, case_id)
    case_sent = step_sent_attach(structure_type2, case_id)
    case_sentence_final = step_sentence_role(case_sent, case_id)

    nodes, blocks = step_bravo_tree(case_sentence_final, case_id)
    narrative = step_narrative(blocks, case_id)

    keyword_map, signature_data, cluster_data = step_keywords(narrative, case_id)
    issue_frame = step_issue_frame(blocks, cluster_data, case_id)
    issue_logic = step_issue_logic(blocks, case_id)

    statutes = structure_raw["statutes"]
    merged_issue_logic = step_issue_citations(issue_logic, statutes, case_id)

    return {
        "metadata": structure_raw["metadata"],
        "narrative": narrative,
        "issue_frame": issue_frame,
        "issue_logic": merged_issue_logic
    }

