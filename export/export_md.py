from jinja2 import Environment, FileSystemLoader
import json
from pathlib import Path


from pathlib import Path
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent.parent   # 27-Delta/ 폴더
TEMPLATE_DIR = BASE_DIR / "templates"

env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

def export_A_to_md(case_id: str):
    data_path = f"cache/{case_id}/export_A_full.json"
    data = json.load(open(data_path, encoding="utf-8"))

    # executive summary 내부 구조 잡기
    exec_summary = data["executive_summary"]["executive_summary"]

    # body 파트
    body = data["body"]
    metadata = body["metadata"]
    narrative = body["narrative"]

    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("report_A_full.md.j2")

    md_output = template.render(
        case_id=case_id,
        exec_summary=exec_summary,
        metadata=metadata,
        narrative=narrative
    )

    out_path = Path(f"cache/{case_id}/report_A_full.md")
    out_path.write_text(md_output, encoding="utf-8")

    return str(out_path)



def export_B_to_md(case_id: str):
    data_path = f"cache/{case_id}/export_B_full.json"
    data = json.load(open(data_path, encoding="utf-8"))

    exec_summary = data["executive_summary"]["executive_summary"]

    body = data["body"]
    metadata = body["metadata"]
    narrative = body["narrative"]
    issue_frame = body["issue_frame"]
    statutes = body["statutes"]

    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("report_B_full.md.j2")

    md_output = template.render(
        case_id=case_id,
        exec_summary=exec_summary,
        metadata=metadata,
        narrative=narrative,
        issue_frame=issue_frame,
        statutes=statutes
    )

    out_path = Path(f"cache/{case_id}/report_B_full.md")
    out_path.write_text(md_output, encoding="utf-8")

    return str(out_path)


def export_C_to_md(case_id: str):
    data_path = f"cache/{case_id}/export_C_full.json"
    data = json.load(open(data_path, encoding="utf-8"))

    exec_summary = data["executive_summary"]["executive_summary"]

    body = data["body"]
    metadata = body["metadata"]
    narrative = body["narrative"]
    issue_logic = body["issue_logic"]
    statutes = body["statutes"]

    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("report_C_full.md.j2")

    es = exec_summary  # 보기 편하게

    md_output = template.render(
        case_id = case_id,

        # exec_summary 안의 모든 필드를 펼쳐서 템플릿에 공급
        one_liner = es["one_liner"],
        core_issues = es["core_issues"],
        how_the_court_thought = es["judicial_logic"]["how_the_court_thought"],
        legal_context = es["judicial_logic"]["legal_context"],

        taxpayer = es["party_positions"]["taxpayer"],
        tax_authority = es["party_positions"]["tax_authority"],
        contrasting_points = es["party_positions"]["contrasting_points"],

        taxpayer_risk = es["risk_view"]["taxpayer_risk"],
        tax_authority_risk = es["risk_view"]["tax_authority_risk"],
        precedent_signal = es["risk_view"]["precedent_signal"],

        metadata = metadata,
        narrative = narrative,
        issue_logic = issue_logic,
        statutes = statutes,
    )

    out_path = Path(f"cache/{case_id}/report_C_full.md")
    out_path.write_text(md_output, encoding="utf-8")

    return str(out_path)


import pypandoc

def md_to_docx(md_path: str):
    docx_path = md_path.replace(".md", ".docx")
    pypandoc.convert_file(
        md_path,
        'docx',
        outputfile=docx_path
    )
    return docx_path
