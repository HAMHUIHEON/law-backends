from jinja2 import Environment, FileSystemLoader
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent   # 27-Delta/ 폴더
TEMPLATE_DIR = BASE_DIR / "templates"

env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

def export_A_to_md(case_id: str):
    from utils.cache import load_cache, save_cache
    data = load_cache(case_id, "export_A_full.json")
    if data is None:
        raise RuntimeError("export_A_full.json not found")

    # executive summary 내부 구조 잡기
    exec_summary = data["executive_summary"]["executive_summary"]

    # body 파트
    body = data["body"]
    metadata = body["metadata"]
    narrative = body["narrative"]

    template = env.get_template("report_A_full.md.j2")

    md_output = template.render(
        case_id=case_id,
        exec_summary=exec_summary,
        metadata=metadata,
        narrative=narrative
    )

    save_cache(case_id, "report_A_full.md", md_output)
    return "report_A_full.md"



def export_B_to_md(case_id: str):
    from utils.cache import load_cache, save_cache
    data = load_cache(case_id, "export_B_full.json")
    if data is None:
        raise RuntimeError("export_B_full.json not found")

    exec_summary = data["executive_summary"]["executive_summary"]

    body = data["body"]
    metadata = body["metadata"]
    narrative = body["narrative"]
    issue_frame = body["issue_frame"]
    statutes = body["statutes"]

    template = env.get_template("report_B_full.md.j2")

    md_output = template.render(
        case_id=case_id,
        exec_summary=exec_summary,
        metadata=metadata,
        narrative=narrative,
        issue_frame=issue_frame,
        statutes=statutes
    )

    save_cache(case_id, "report_B_full.md", md_output)
    return "report_B_full.md"


def export_C_to_md(case_id: str):
    from utils.cache import load_cache, save_cache
    data = load_cache(case_id, "export_C_full.json")
    if data is None:
        raise RuntimeError("export_C_full.json not found")

    exec_summary = data["executive_summary"]["executive_summary"]

    body = data["body"]
    metadata = body["metadata"]
    narrative = body["narrative"]
    issue_logic = body["issue_logic"]
    statutes = body["statutes"]

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

    save_cache(case_id, "report_C_full.md", md_output)
    return "report_C_full.md"


