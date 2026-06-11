# stage10_citation.py

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
        # cached를 실제 issue_logic에 merge해줘야 함
        return attach_citations(issue_logic, cached)

    chain = BravoIssueCitationChain()
    outputs = []

    # issue_logic_chains: Pydantic 객체 리스트
    for chain_item in issue_logic.issue_logic_chains:
        out = run_attach_issue_citation(chain_item, chain)
        outputs.append(out)

    result = {
        "issue_citations": [o.model_dump() for o in outputs]
    }

    save_cache(case_id, "issue_logic_citations.json", result)

    # 🔥 여기서 attach 실행
    merged = attach_citations(issue_logic, result)
    save_cache(case_id, "issue_logic_with_citations.json", merged.model_dump())

    return merged



def attach_citations(issue_logic, citation_result):
    """
    citation_result = {
        "issue_citations": [
            { "issue": ..., "citations": [...] },
            ...
        ]
    }
    """

    citation_map = {item["issue"]: item["citations"]
                    for item in citation_result["issue_citations"]}

    # issue_logic은 BravoGlobalOutline 객체
    for chain in issue_logic.issue_logic_chains:
        chain.citations = citation_map.get(chain.issue, [])

    return issue_logic
