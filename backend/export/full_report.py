from utils.llm import DEFAULT_MODEL
#export/full_report.py
from export.export_a import build_export_A
from export.export_b import build_export_B
from export.export_c import build_export_C
from export.export_chain import ExportAChain
from export.run import run_export_case_A, run_export_case_B, run_export_case_C
from export.export_md import export_A_to_md,export_B_to_md,export_C_to_md
from export.export_docx import export_A_to_docx,export_B_to_docx,export_C_to_docx
#=======================
# export A/B/C pipeline
#=======================

def run_export_pipeline_A(case_id: str, model: str = DEFAULT_MODEL):
    build_export_A(case_id)

    chain = ExportAChain(model=model)
    run_export_case_A(case_id, chain)
    
    full_json_path = build_full_report_A(case_id)

    # 🔥 MD 생성
    md_path = export_A_to_md(case_id)
    # 🔥 DOCX 생성
    docx_path = export_A_to_docx(case_id)

    return {
        "json": full_json_path,
        "md": md_path,
        "docx": docx_path
    }

def run_export_pipeline_B(case_id: str, model: str = DEFAULT_MODEL):
    # 1) raw export build
    build_export_B(case_id)

    # 2) run export case B (체인 내부 생성)
    run_export_case_B(case_id, model=model)

    # 3) merge + produce final report
    full_json_path = build_full_report_B(case_id)

    # 🔥 MD 생성
    md_path = export_B_to_md(case_id)
    # 🔥 DOCX 생성
    docx_path = export_B_to_docx(case_id)

    return {
        "json": full_json_path,
        "md": md_path,
        "docx": docx_path,
    }



def run_export_pipeline_C(case_id: str, model: str = DEFAULT_MODEL):
    # 1) build raw export structure
    build_export_C(case_id)

    # 2) run export case C (체인 내부 생성)
    run_export_case_C(case_id, model=model)

    # 3) merge + produce final report
    full_json_path = build_full_report_C(case_id)

    # 🔥 MD 생성
    md_path = export_C_to_md(case_id)
    # 🔥 DOCX 생성
    docx_path = export_C_to_docx(case_id)

    return {
        "json": full_json_path,
        "md": md_path,
        "docx": docx_path,
    }



#=========================
# build full report A/B/C 
#=========================
#A
def build_full_report_A(case_id: str):
    from utils.cache import load_cache, save_cache

    # 1) 원본 데이터(body)
    base = {
        "metadata": load_cache(case_id, "metadata.json"),
        "narrative": load_cache(case_id, "narrative.json"),
    }

    # 2) LLM 썸머리(exec)
    exec_summary = load_cache(case_id, "export_A_exec_summary.json")

    # 3) 병합
    full = {
        "executive_summary": exec_summary,
        "body": base
    }

    # 4) 저장
    return save_cache(case_id, "export_A_full.json", full)

#B
def build_full_report_B(case_id: str):
    from utils.cache import load_cache, save_cache

    base = {
        "metadata": load_cache(case_id, "metadata.json"),
        "narrative": load_cache(case_id, "narrative.json"),
        "issue_frame": load_cache(case_id, "issue_frame.json"),
        "statutes":load_cache(case_id, "statutes.json")
    }

    exec_summary = load_cache(case_id, "export_B_exec_summary.json")

    full = {
        "executive_summary": exec_summary,
        "body": base
    }

    return save_cache(case_id, "export_B_full.json", full)

#C
def build_full_report_C(case_id: str):
    from utils.cache import load_cache, save_cache

    base = {
        "metadata": load_cache(case_id, "metadata.json"),
        "narrative": load_cache(case_id, "narrative.json"),
        "issue_logic": load_cache(case_id, "issue_logic_with_citations.json"),
        "statutes": load_cache(case_id, "statutes.json"),
    }

    exec_summary = load_cache(case_id, "export_C_exec_summary.json")

    full = {
        "executive_summary": exec_summary,
        "body": base
    }

    return save_cache(case_id, "export_C_full.json", full)