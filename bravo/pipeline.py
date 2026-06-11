# bravo/pipeline.py

from bravo.init_fields import init_bravo_fields
from bravo.input_builder import build_bravo_global_chunks
from bravo.models_bravo import (BravoIssueCitationInput,BravoIssueCitationOutput,
                                BravoTopicInput,BravoIssueInput,
                                BravoGlobalInput, IssueGroup,BravoSignatureOutput,
                                BravoGlobalOutline,BravoIssueOutput,BravoNarrativeOutput)
from prime.node_builder import build_prime_nodes
from prime.builder import build_prime_blocks
from bravo.chain import (BravoGlobalChain, BravoIssueCitationChain,
                         BravoSignatureChain,ReasoningIssueChain,
                         BravoKeywordChain,BravoNarrativeChain)
from typing import List, Optional, Dict


# Pass2-Citation
def run_attach_issue_citation(issue_logic_item, chain: BravoIssueCitationChain) -> BravoIssueCitationOutput:
    
    full_text_parts = [
        issue_logic_item.premise,
        issue_logic_item.evidence,
        issue_logic_item.rule,
        issue_logic_item.application,
        issue_logic_item.inference,
        issue_logic_item.mini_conclusion,
    ]

    full_text = "\n".join([p for p in full_text_parts if p])

    # 2) LLM 입력 모델 만들기
    inp = BravoIssueCitationInput(
        issue=issue_logic_item.issue,
        full_text=full_text,
    )

    # 3) 체인 실행
    return chain.extract(inp)
    

#Pass1
def run_global_outline(chunks: list[str], chain: BravoGlobalChain):
    results = []

    for ch in chunks:
        out = chain.summarize(ch)
        results.append(out)

    return merge_global_outlines(results)

import re

_ws_re = re.compile(r"\s+")

def normalize_issue(s: str) -> str:
    return _ws_re.sub(" ", s.strip())

import hashlib

def make_uid(issue: str) -> str:
    return hashlib.sha256(issue.encode("utf-8")).hexdigest()[:12]

def merge_global_outlines(outlines: list[BravoGlobalOutline]) -> BravoGlobalOutline:
    merged_global_outline = []
    merged_main_issues = []
    merged_issue_logic = []

    seen_paragraphs = set()
    seen_issues = set()

    for o in outlines:
        if isinstance(o.global_outline, str) and o.global_outline.strip():
            p = o.global_outline.strip()
            if p not in seen_paragraphs:
                seen_paragraphs.add(p)
                merged_global_outline.append(p)

        if getattr(o, "main_issues", None):
            for iss in o.main_issues:
                if iss not in merged_main_issues:
                    merged_main_issues.append(iss)

        if getattr(o, "issue_logic_chains", None):
            for ch in o.issue_logic_chains:
                issue = normalize_issue(ch.issue)
                if issue in seen_issues:
                    continue

                seen_issues.add(issue)

                ch.issue = issue
                ch.uid = make_uid(issue)
                merged_issue_logic.append(ch)


    return BravoGlobalOutline(
        global_outline="\n\n".join(merged_global_outline).strip(),
        main_issues=merged_main_issues,
        issue_logic_chains=merged_issue_logic,
    )


#pass0
def extract_representative_keywords(signature_json: dict) -> List[str]:
    return list(signature_json["clusters"].keys())

def run_reasoning_issues(blocks,
                         representative_keywords,
                         chain: ReasoningIssueChain):

    chunks = []

    for chunk in chunks:
        inp = BravoIssueInput(
            full_text=chunk,
            keywords=representative_keywords
        )
        out = chain.extract(inp)
        chunks.append(out)

    return merge_issue_outputs(chunks)

from typing import List, Dict
from bravo.models_bravo import IssueGroup, BravoIssueOutput

def merge_issue_outputs(outputs: List[BravoIssueOutput]) -> BravoIssueOutput:
    # 최종적으로 BravoIssueOutput에 넣을 순수 dict 구조
    merged: Dict[str, dict] = {}

    for out in outputs:
        # out이 dict로 들어올 가능성까지 방어
        if isinstance(out, dict):
            data = out
        else:
            data = out.model_dump()

        for key, group_dict in data.get("issue_groups", {}).items():
            # group_dict가 이미 dict일 거라고 가정 (LLM JSON 그대로)
            # 혹시 모르니 한번 더 dict 강제
            if isinstance(group_dict, IssueGroup):
                group_dict = group_dict.model_dump()

            mg = merged.setdefault(key, {
                "plaintiff_arguments": [],
                "defendant_arguments": [],
                "legal_context": [],
                "court_reasoning": [],
            })

            mg["plaintiff_arguments"].extend(group_dict.get("plaintiff_arguments") or [])
            mg["defendant_arguments"].extend(group_dict.get("defendant_arguments") or [])
            mg["legal_context"].extend(group_dict.get("legal_context") or [])
            mg["court_reasoning"].extend(group_dict.get("court_reasoning") or [])

    final_data = {"issue_groups": merged}
    return BravoIssueOutput.model_validate(final_data)


#pass_base_b-1
def run_cluster_issue_keywords(keyword_map: dict, chain: BravoSignatureChain) -> BravoSignatureOutput:
    """
    keyword_map: {issue: [keywords...]} 형태
    → 전체 키워드를 flatten해서 clustering
    """
    # 모든 키워드 flatten + dedupe
    all_keywords = set()
    for kws in keyword_map.values():
        for kw in kws:
            all_keywords.add(kw)

    all_keywords = sorted(all_keywords)

    print(f"[DEBUG] 총 키워드 수: {len(all_keywords)}")
    return chain.cluster(all_keywords)



#pass_base_b
def run_extract_issue_keywords(core_conflicts: List[str], chain: BravoKeywordChain):
    results = {}

    for conf in core_conflicts:
        out = chain.extract(conf)
        results[conf] = out.keywords

    return results

#pass_base_a
def run_narrative(chunks, chain: BravoNarrativeChain) -> BravoNarrativeOutput:
    merged = {
        "fact_summary": "",
        "plaintiff_arguments": [],
        "defendant_arguments": [],
        "legal_context": [],
        "court_reasoning": [],
        "core_conflicts": []
    }

    for ch in chunks:
        out = chain.narrative(BravoTopicInput(full_text=ch))
        if not out:
            continue

        # 1) 문자열 필드
        for k in ["fact_summary"]:
            part = getattr(out, k, None)
            if isinstance(part, str):
                part = part.strip()
                if part and part not in merged[k]:
                    merged[k] += ("\n" + part if merged[k] else part)

        # 2) 리스트 필드
        for k in ["plaintiff_arguments", "defendant_arguments", "legal_context", "court_reasoning", "core_conflicts"]:
            part_list = getattr(out, k, [])
            if isinstance(part_list, list):
                for item in part_list:
                    item = item.strip()
                    if item and item not in merged[k]:
                        merged[k].append(item)

    return BravoNarrativeOutput(**merged)
