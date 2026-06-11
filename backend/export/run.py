from utils.llm import DEFAULT_MODEL
#export/run.py
from __future__ import annotations

from typing import Any, Dict, List
import json
from utils.cache import load_cache, save_cache
from export.export_chain import ExportAChain, ExportBChain,ExportCChain
from export.models_export import (ExportAInput,ExportBInput,ExportBOutput,
                                  ExportCExecSummary,ExportCInput,ExportCOutput)
from export.prompt import EXPORT_C_PROMPT, PARTIAL_PREFIX, B_PARTIAL_PREFIX, B, REDUCE_PREFIX


from typing import Any, Dict, List, Optional, Literal
from pathlib import Path
import json
import time
import random
import hashlib

from bravo.models_bravo import IssueLogic




#=========================
# run export case A  (유틸 및 런함수)
#=========================

def run_export_case_A(case_id: str, chain: ExportAChain):
    from utils.cache import load_cache, save_cache


    # 1) 필요한 캐쉬 로드
    narrative = load_cache(case_id, "narrative.json")      # dict
    # 2) LLM input 구성
    inp = ExportAInput(
        narrative_json=narrative,
    )

    # 3) LLM 실행
    result = chain.run(inp)

    # 4) 저장 (🔥 반드시 save_cache)
    return save_cache(
        case_id,
        "export_A_exec_summary.json",
        result.model_dump(),
    )

#=========================
# run export case B  (유틸 및 런함수)
#=========================
def estimate_issue_tokens(issue: dict) -> int:
    """
    issue 하나(이슈 타이틀 + arguments + reasoning 등)의
    보수적 토큰 추정치
    """
    text = json.dumps(issue, ensure_ascii=False)
    # 매우 보수적으로: 1 token ≈ 3 chars
    return max(300, len(text) // 3)


def chunk_issues_by_token(
    issues: list[dict],
    max_est_tokens: int = 6000,
) -> list[list[dict]]:
    chunks = []
    current = []
    current_tokens = 0

    for issue in issues:
        est = estimate_issue_tokens(issue)

        # 단일 issue가 너무 큰 경우 → 단독 chunk
        if est > max_est_tokens:
            if current:
                chunks.append(current)
                current = []
                current_tokens = 0
            chunks.append([issue])
            continue

        if current_tokens + est > max_est_tokens:
            chunks.append(current)
            current = [issue]
            current_tokens = est
        else:
            current.append(issue)
            current_tokens += est

    if current:
        chunks.append(current)

    return chunks

def flatten_issue_groups(issue_groups: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    issue_groups(dict[str, dict]) → section list로 평탄화
    section은 issue_group 1개를 의미 단위로 유지한다.
    """
    sections: List[Dict[str, Any]] = []
    for title, body in issue_groups.items():
        if not isinstance(body, dict):
            # 예상 구조가 아니면 그대로 넣되 최소한 title만 보존
            sections.append({"issue_title": title, "issue": body})
            continue

        sections.append({"issue_title": title, **body})
    return sections




def run_export_case_B(
    case_id: str,
    *,
    model: str = DEFAULT_MODEL,
    max_est_tokens: int = 6500,
) -> str:
    from utils.cache import load_cache, save_cache

    # =========================
    # 0️⃣ 캐시 히트 → 바로 리턴
    # =========================
    cached = load_cache(case_id, "export_B_exec_summary.json")
    if cached is not None:
        print(f"[Export B] cache hit → skip LLM ({case_id})")
        return "export_B_exec_summary.json"

    # =========================
    # 1️⃣ 필요한 캐시 로드
    # =========================
    narrative = load_cache(case_id, "narrative.json")
    issue_frame = load_cache(case_id, "issue_frame.json")

    issue_groups = issue_frame.get("issue_groups", {})
    sections = flatten_issue_groups(issue_groups)
    if not sections:
        raise ValueError("issue_groups is empty")

    chunks = chunk_issues_by_token(
        issues=sections,
        max_est_tokens=max_est_tokens,
    )

    partial_chain = ExportBChain(
        model=model,
        prompt_template=B_PARTIAL_PREFIX + B,
    )
    final_chain = ExportBChain(
        model=model,
        prompt_template=B,
    )

    chunk_results = []

    for i, chunk in enumerate(chunks, start=1):
        print(f"[Export B] issue chunk {i}/{len(chunks)}")

        chunk_issue_frame = {
            "issue_groups": {
                s["issue_title"]: {k: v for k, v in s.items() if k != "issue_title"}
                for s in chunk
            }
        }

        inp = ExportBInput(
            narrative_json=narrative,
            issue_frame=chunk_issue_frame,
        )

        result = partial_chain.run(inp)
        chunk_results.append(result.model_dump())

    final_inp = ExportBInput(
        narrative_json=narrative,
        issue_frame={"chunk_summaries": chunk_results},
    )

    final_result = final_chain.run(final_inp)

    return save_cache(
        case_id,
        "export_B_exec_summary.json",
        final_result.model_dump(),
    )


# =========================
# Export C (CLEAN & FINAL)
# =========================

# -----------------------------------------------------
# 1) Token/packing utils (보수적 추정)
# -----------------------------------------------------
def estimate_tokens(text: str) -> int:
    # 기존 네 경험치 유지 (보수)
    return int(len(text) * 2.2)


def pack_strings_by_token(items: List[str], *, max_tokens: int) -> List[List[str]]:
    """
    List[str]를 토큰 예산으로 여러 pack(List[str])으로 묶는다.
    - 단일 항목이 예산을 초과하면 그 항목 단독 pack으로 둔다.
    """
    packs: List[List[str]] = []
    buf: List[str] = []
    buf_tokens = 0

    for s in items:
        t = estimate_tokens(s)
        if not buf:
            buf = [s]
            buf_tokens = t
            continue

        if buf_tokens + t <= max_tokens:
            buf.append(s)
            buf_tokens += t
        else:
            packs.append(buf)
            buf = [s]
            buf_tokens = t

    if buf:
        packs.append(buf)
    return packs


def estimate_export_c_tokens(issue_logic_list: List[IssueLogic], block_texts: List[str]) -> int:
    issue_part = json.dumps([it.model_dump() for it in issue_logic_list], ensure_ascii=False)
    block_part = json.dumps(block_texts, ensure_ascii=False)
    return estimate_tokens(issue_part + block_part)


# -----------------------------------------------------
# 2) Retry (Cloudflare / Origin DNS)
# -----------------------------------------------------
def run_with_retry(fn, *, max_retries: int = 6, base_wait: float = 4.0):
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as e:
            msg = str(e) or ""
            transient = ("Origin DNS error" in msg) or ("Cloudflare" in msg)
            if (not transient) or (attempt == max_retries):
                raise
            wait = base_wait * attempt + random.uniform(0, 2.5)
            print(f"[Retry] transient error; retrying in {wait:.1f}s ({attempt}/{max_retries})")
            time.sleep(wait)


# -----------------------------------------------------
# 3) Cache helpers
# -----------------------------------------------------
def _read_json_safely(path: Path) -> Optional[Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def export_c_final_cache_path(case_id: str) -> Path:
    d = Path(f"cache/{case_id}")
    d.mkdir(parents=True, exist_ok=True)
    return d / "export_C_exec_summary.json"


def export_c_doc_digest_cache_path(case_id: str) -> Path:
    d = Path(f"cache/{case_id}/export_C")
    d.mkdir(parents=True, exist_ok=True)
    return d / "doc_digest.json"


def export_c_issue_chunk_cache_path(case_id: str, issue_key: str) -> Path:
    d = Path(f"cache/{case_id}/export_C/issue_chunk")
    d.mkdir(parents=True, exist_ok=True)
    return d / f"issue_{issue_key}.json"


def _safe_issue_key(issue_chunk: List[IssueLogic]) -> str:
    # IssueLogic에 id가 없다고 했으니 issue 문자열 기반으로 안정 키
    raw = "||".join(getattr(i, "issue", "") for i in issue_chunk)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


# -----------------------------------------------------
# 4) Chain factory
# -----------------------------------------------------
from typing import Literal

def make_export_c_chain(model: str, mode: Literal["partial", "reduce", "final"]) -> ExportCChain:
    if mode == "partial":
        prompt_template = PARTIAL_PREFIX + EXPORT_C_PROMPT
    elif mode == "reduce":
        prompt_template = REDUCE_PREFIX + EXPORT_C_PROMPT
    else:
        prompt_template = EXPORT_C_PROMPT

    return ExportCChain(model=model, prompt_template=prompt_template)



# -----------------------------------------------------
# 5) Chunking helpers
# -----------------------------------------------------
def chunk_issue_logic(issue_logic_list: List[IssueLogic], *, max_issues: int = 2) -> List[List[IssueLogic]]:
    chunks: List[List[IssueLogic]] = []
    buf: List[IssueLogic] = []
    for issue in issue_logic_list:
        buf.append(issue)
        if len(buf) >= max_issues:
            chunks.append(buf)
            buf = []
    if buf:
        chunks.append(buf)
    return chunks


def build_export_global_chunks(blocks: Any, max_len: int = 2000) -> List[str]:
    """
    BravoBlock 기반 글로벌 chunk.
    blocks: load_cache(case_id, "bravo_blocks.json") 결과를 그대로 받는다.
    """
    block_texts: List[str] = []
    for b in blocks:
        txt = "\n".join(n["text"] for n in b["nodes"])
        if txt.strip():
            block_texts.append(txt.strip())

    chunks: List[str] = []
    buf = ""

    for block_txt in block_texts:
        if len(buf) + len(block_txt) + 2 <= max_len:
            buf += block_txt + "\n\n"
        else:
            if buf.strip():
                chunks.append(buf.strip())
            buf = block_txt + "\n\n"

    if buf.strip():
        chunks.append(buf.strip())

    return chunks


# -----------------------------------------------------
# 6) Reduce-until-one (핵심)
# -----------------------------------------------------
def reduce_texts_until_one(
    *,
    texts: List[str],
    issue_logic_list: List[IssueLogic],
    model: str,
    budget_tokens: int,
    label: str,
) -> str:
    """
    texts(List[str])를 budget_tokens에 맞춰 pack 후 reduce를 반복해
    최종 1개의 JSON string(= executive_summary dict의 json dumps)을 만든다.
    """
    reduce_chain = make_export_c_chain(model=model, mode="reduce")

    cur = texts[:]
    round_no = 0

    while len(cur) > 1:
        round_no += 1
        packs = pack_strings_by_token(cur, max_tokens=budget_tokens)
        print(f"[{label}] reduce round {round_no}: {len(cur)} items -> {len(packs)} packs (budget={budget_tokens})")

        next_cur: List[str] = []
        for p_idx, pack in enumerate(packs, start=1):
            inp = ExportCInput(issue_logic_list=issue_logic_list, block_texts=pack)  # List[str]
            out: ExportCOutput = run_with_retry(lambda: reduce_chain.run(inp))
            next_cur.append(json.dumps(out.executive_summary.model_dump(), ensure_ascii=False))
            print(f"  - pack {p_idx}/{len(packs)} reduced")

        cur = next_cur

    return cur[0]


# -----------------------------------------------------
# 7) Main: run_export_case_C (NO ISSUE×BLOCK)
# -----------------------------------------------------
def run_export_case_C(case_id: str, model: str = DEFAULT_MODEL) -> ExportCOutput:
    MAX_SAFE_TOKENS = 220_000
    REDUCE_BUDGET = 120_000  # reduce 안정 예산

    # 0️⃣ final cache
    cached_final = load_cache(case_id, "export_C_exec_summary.json")
    if cached_final is not None:
        return ExportCOutput(**cached_final)

    # 1) load inputs
    raw_issue_logic = load_cache(case_id, "issue_logic_with_citations.json")
    issue_logic_items = (
        raw_issue_logic["issue_logic_chains"]
        if isinstance(raw_issue_logic, dict) and "issue_logic_chains" in raw_issue_logic
        else raw_issue_logic
    )
    issue_logic_list: List[IssueLogic] = [IssueLogic(**item) for item in issue_logic_items]

    blocks = load_cache(case_id, "bravo_blocks.json")
    block_texts: List[str] = build_export_global_chunks(blocks)

    est = estimate_export_c_tokens(issue_logic_list, block_texts)
    print(f"[ExportC] estimated tokens = {est:,}")

    # 2️⃣ single-shot
    if est <= MAX_SAFE_TOKENS:
        print("[ExportC] single-shot mode")
        final_chain = make_export_c_chain(model=model, mode="final")
        inp = ExportCInput(issue_logic_list=issue_logic_list, block_texts=block_texts)
        out: ExportCOutput = run_with_retry(lambda: final_chain.run(inp))
        save_cache(case_id, "export_C_exec_summary.json", out.model_dump())
        return out

    # 3️⃣ chunked mode
    print("[ExportC] chunked mode")

    # 3-A) doc_digest (cached)
    cached_doc = load_cache(case_id, "export_C/doc_digest.json")

    if isinstance(cached_doc, dict) and isinstance(cached_doc.get("doc_digest"), str) and cached_doc["doc_digest"].strip():
        doc_digest_str: str = cached_doc["doc_digest"]
    else:
        print(f"[ExportC] building doc_digest from {len(block_texts)} blocks")
        # doc_digest는 이슈로직 없이 문서만 요약(토큰/편향 최소화)
        empty_issues: List[IssueLogic] = []
        doc_digest_str = reduce_texts_until_one(
            texts=block_texts,
            issue_logic_list=empty_issues,
            model=model,
            budget_tokens=REDUCE_BUDGET,
            label="DocReduce",
        )
        save_cache(case_id, "export_C/doc_digest.json", {"doc_digest": doc_digest_str})

    # 3-B) issue_chunk별 final 실행 (doc_digest만 투입) + 캐시
    issue_chunks = chunk_issue_logic(issue_logic_list, max_issues=2)
    print(f"[ExportC] issue chunks = {len(issue_chunks)}")

    final_chain = make_export_c_chain(model=model, mode="final")
    issue_level_strings: List[str] = []

    for idx, issue_chunk in enumerate(issue_chunks, start=1):
        issue_key = _safe_issue_key(issue_chunk)
        cache_key = f"export_C/issue_chunk/issue_{issue_key}.json"

        cached_issue = load_cache(case_id, cache_key)
        if isinstance(cached_issue, dict) and isinstance(cached_issue.get("issue_chunk_summary"), str) and cached_issue["issue_chunk_summary"].strip():
            issue_level_strings.append(cached_issue["issue_chunk_summary"])
            continue

        print(f"[IssueChunk {idx}/{len(issue_chunks)}] run (issue_key={issue_key})")

        inp = ExportCInput(
            issue_logic_list=issue_chunk,
            block_texts=[doc_digest_str],
        )
        out: ExportCOutput = run_with_retry(lambda: final_chain.run(inp))
        s = json.dumps(out.executive_summary.model_dump(), ensure_ascii=False)

        save_cache(case_id, cache_key, {"issue_chunk_summary": s})
        issue_level_strings.append(s)

    # -------------------------------------------------
    # 3-C) FINAL REDUCE (REDUCE, CACHED)
    # -------------------------------------------------
    cached_reduce = load_cache(case_id, "export_C/final_reduce.json")

    if isinstance(cached_reduce, dict) and isinstance(cached_reduce.get("merged_issue_str"), str):
        merged_issue_str = cached_reduce["merged_issue_str"]
    else:
        merged_issue_str = reduce_texts_until_one(
            texts=issue_level_strings,
            issue_logic_list=[],
            model=model,
            budget_tokens=REDUCE_BUDGET,
            label="FinalReduce",
        )
        save_cache(case_id, "export_C/final_reduce.json", {"merged_issue_str": merged_issue_str})

    # -------------------------------------------------
    # FINAL OUTPUT (no extra wrap)
    # -------------------------------------------------

    # merged_issue_str 는 이미 REDUCE 단계에서
    # ExportCOutput.executive_summary 를 JSON 문자열로 만든 것
    final_obj = {
        "executive_summary": json.loads(merged_issue_str)
    }

    save_cache(case_id, "export_C_exec_summary.json", final_obj)
    return ExportCOutput(**final_obj)

