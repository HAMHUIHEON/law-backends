# stage10_citation.py

from concurrent.futures import ThreadPoolExecutor
from bravo.chain import BravoIssueCitationChain
from bravo.pipeline import run_attach_issue_citation
from bravo.models_bravo import BravoGlobalOutline


def step_issue_citations(issue_logic, statutes, case_id):
    from utils.cache import load_cache, save_cache

    # 1) dict → BravoGlobalOutline 변환
    if isinstance(issue_logic, dict):
        issue_logic = BravoGlobalOutline(**issue_logic)

    cached = load_cache(case_id, "issue_logic_citations.json")
    if cached:
        return attach_citations(issue_logic, cached)

    chain = BravoIssueCitationChain()

    with ThreadPoolExecutor(max_workers=5) as exe:
        outputs = list(exe.map(
            lambda item: run_attach_issue_citation(item, chain),
            issue_logic.issue_logic_chains
        ))

    result = {
        "issue_citations": [o.model_dump() for o in outputs]
    }

    save_cache(case_id, "issue_logic_citations.json", result)

    # 버전 매칭 실행 (is_prior_version=True이고 promulgation_no 있는 것만)
    result = _resolve_versions(result)
    save_cache(case_id, "issue_logic_citations_resolved.json", result)

    merged = attach_citations(issue_logic, result)
    save_cache(case_id, "issue_logic_with_citations.json", merged.model_dump())

    return merged


def _resolve_versions(citation_result: dict) -> dict:
    """
    추출된 citation 중 is_prior_version=True이고 promulgation_no가 있는 것에 대해
    Neo4j(ITCL) 또는 Claude 지식으로 법령 버전을 매칭합니다.
    """
    from utils.statute_version import resolve_citation_version
    from bravo.models_bravo import CitationItem

    for issue_entry in citation_result.get("issue_citations", []):
        resolved_citations = []
        for cit_dict in issue_entry.get("citations", []):
            try:
                cit = CitationItem(**cit_dict)
                if cit.is_prior_version and cit.promulgation_no:
                    matched = resolve_citation_version(cit)
                    cit_dict = cit.model_dump()
                    cit_dict["matched_version"] = matched
                resolved_citations.append(cit_dict)
            except Exception:
                resolved_citations.append(cit_dict)
        issue_entry["citations"] = resolved_citations

    return citation_result


def attach_citations(issue_logic, citation_result):
    citation_map = {item["issue"]: item["citations"]
                    for item in citation_result["issue_citations"]}

    for chain in issue_logic.issue_logic_chains:
        chain.citations = citation_map.get(chain.issue, [])

    return issue_logic
