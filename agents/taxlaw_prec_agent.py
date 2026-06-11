"""
taxlaw.nts.go.kr 법원 판례 에이전트

국세청이 수집·분류한 세법 법원 판례(62,000+건)를 검색하고 분석합니다.
국승/국패 분류, 세법 분류, 전문(98%) 보유.

사용:
    from agents.taxlaw_prec_agent import TaxlawPrecAgent

    agent = TaxlawPrecAgent()
    response = agent.ask("법인세 이전가격 관련 국패 판례 있나요?")
    response = agent.ask("양도소득세 비과세 요건 관련 납세자가 이긴 사례 알려줘")
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Iterator, Optional

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from utils.llm import get_llm, DEFAULT_MODEL

ROOT       = Path(__file__).parent.parent
JSONL_PATH = ROOT / "taxlaw" / "data" / "prec" / "prec.jsonl"
CHROMA_DIR = ROOT / "vector_db" / "chroma"
COLLECTION = "taxlaw_prec"

# 사용자 입력 → Chroma 저장값 매핑 (NTST_TLAW_CL_NM 기준)
TAX_TYPE_MAP: dict[str, str] = {
    "법인세": "법인세", "법인": "법인세",
    "소득세": "종합소득세", "종합소득세": "종합소득세", "종합소득": "종합소득세",
    "양도소득세": "양도소득세", "양도": "양도소득세",
    "부가가치세": "부가가치세", "부가세": "부가가치세", "부가": "부가가치세",
    "상속세": "상속증여세", "증여세": "상속증여세", "상속증여": "상속증여세",
    "종합부동산세": "종합부동산세", "종부세": "종합부동산세",
    "국세징수": "국세징수", "징수": "국세징수",
    "국세기본": "국세기본", "국기법": "국세기본",
    "국제조세": "국제조세", "이전가격": "국제조세",
}

# 국가 패소 = 납세자 승소 방향
WINNING_DECISIONS = {"국패", "일부국패", "일부국승"}

# 결정유형 사용자 입력 → 저장값
DECISION_MAP: dict[str, str] = {
    "국승": "국승", "국가승소": "국승", "납세자패소": "국승",
    "국패": "국패", "국가패소": "국패", "납세자승소": "국패",
    "일부국패": "일부국패", "일부승소": "일부국패",
    "각하": "각하",
    "기각": "기각",
}


# ── 공통 유틸 ─────────────────────────────────────────────────────────────────

def _get_chroma_collection():
    import chromadb
    from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

    ef = OpenAIEmbeddingFunction(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model_name="text-embedding-3-small",
    )
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_collection(COLLECTION, embedding_function=ef)


def _load_by_doc_id(doc_id: str) -> Optional[dict]:
    """JSONL에서 DOC_ID로 레코드 스캔."""
    if not JSONL_PATH.exists():
        return None
    target = str(doc_id).strip()
    with JSONL_PATH.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if str(r.get("DOC_ID", "")).strip() == target:
                    return r
            except json.JSONDecodeError:
                continue
    return None


def _format_brief(meta: dict) -> str:
    parts = []
    if meta.get("case_no"):
        parts.append(f"[{meta['case_no']}]")
    if meta.get("tax_type"):
        parts.append(f"세법:{meta['tax_type']}")
    if meta.get("decision"):
        parts.append(f"결정:{meta['decision']}")
    if meta.get("attr_yr"):
        parts.append(f"기준연도:{meta['attr_yr']}")
    header = " | ".join(parts)
    title = meta.get("title", "")[:80]
    return f"{header}\n  {title}" if title else header


# ── 도구 ──────────────────────────────────────────────────────────────────────

@tool
def search_court_cases(
    query: str,
    tax_type: str = "",
    decision: str = "",
    n_results: int = 8,
) -> str:
    """
    법원 판례 벡터 DB에서 유사 사례를 검색합니다. (taxlaw.nts.go.kr, 32,000+건)

    Parameters
    ----------
    query     : 검색 질의 (예: '이전가격 정상가격 부인 법인세')
    tax_type  : 세법 필터 (예: '법인세', '부가가치세', '양도소득세', '국제조세') — 빈 문자열이면 전체
    decision  : 결정유형 필터 (예: '국패', '국승', '일부국패') — 빈 문자열이면 전체
    n_results : 반환 건수 (기본 8)
    """
    try:
        col = _get_chroma_collection()
    except Exception as e:
        return f"벡터 DB 연결 오류: {e}"

    where_clauses = []
    if tax_type:
        mapped = TAX_TYPE_MAP.get(tax_type.strip(), tax_type.strip())
        where_clauses.append({"tax_type": {"$eq": mapped}})
    if decision:
        mapped_d = DECISION_MAP.get(decision.strip(), decision.strip())
        where_clauses.append({"decision": {"$eq": mapped_d}})

    kwargs: dict = {"query_texts": [query], "n_results": n_results}
    if len(where_clauses) == 1:
        kwargs["where"] = where_clauses[0]
    elif len(where_clauses) > 1:
        kwargs["where"] = {"$and": where_clauses}

    try:
        results = col.query(**kwargs)
    except Exception as e:
        return f"검색 오류: {e}"

    docs  = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    if not docs:
        return "검색 결과 없음"

    lines = [f"'{query}' 관련 법원 판례 {len(docs)}건:\n"]
    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), 1):
        similarity = round(1 - dist, 3)
        lines.append(f"[{i}] 유사도 {similarity} | {_format_brief(meta)}")
        snippet = "\n".join(doc.split("\n")[2:])[:200] if doc else ""
        if snippet:
            lines.append(f"    요지: {snippet}")
        lines.append(f"    → 전문: get_case_detail('{meta.get('doc_id', '')}')")
        lines.append("")

    return "\n".join(lines)


@tool
def get_case_detail(doc_id: str) -> str:
    """
    특정 판례의 전문(全文)을 조회합니다.

    Parameters
    ----------
    doc_id : NTS 문서 ID (예: '200000000000016870')
    """
    r = _load_by_doc_id(doc_id.strip())
    if not r:
        return f"doc_id={doc_id} 판례를 찾을 수 없습니다."

    lines = [
        "=== 법원 판례 상세 ===",
        f"사건번호: {r.get('NTST_DCM_DSCM_CNTN', '')}",
        f"세법:     {r.get('NTST_TLAW_CL_NM', '')}",
        f"결정유형: {r.get('NTST_DCM_DCS_CL_NM', '')}",
        f"기준연도: {r.get('ATTR_YR', '')}",
        "",
        "[쟁점명]",
        r.get("TTL", ""),
        "",
        "[요지]",
        r.get("GIST_CNTN", ""),
    ]

    full_text = r.get("FILE_CN", "").strip()
    if full_text:
        lines += ["", "[전문]", full_text[:3000]]
        if len(full_text) > 3000:
            lines.append(f"... (이하 {len(full_text)-3000}자 생략)")

    return "\n".join(lines)


@tool
def analyze_trend(tax_type: str = "", decision: str = "") -> str:
    """
    법원 판례 결정 트렌드를 분석합니다. (Chroma 메타데이터 기반)

    Parameters
    ----------
    tax_type : 세법 필터 (예: '법인세') — 빈 문자열이면 전체
    decision : 결정유형 필터 (예: '국패') — 빈 문자열이면 전체
    """
    try:
        col = _get_chroma_collection()
    except Exception as e:
        return f"DB 연결 오류: {e}"

    # Chroma에서 전체 메타데이터 가져오기 (배치)
    try:
        result = col.get(include=["metadatas"])
        all_meta = result.get("metadatas", [])
    except Exception as e:
        return f"메타데이터 조회 오류: {e}"

    # 필터 적용
    filtered = []
    tax_mapped = TAX_TYPE_MAP.get(tax_type.strip(), tax_type.strip()) if tax_type else ""
    dec_mapped  = DECISION_MAP.get(decision.strip(), decision.strip()) if decision else ""

    for m in all_meta:
        if tax_mapped and m.get("tax_type") != tax_mapped:
            continue
        if dec_mapped and m.get("decision") != dec_mapped:
            continue
        filtered.append(m)

    total = len(filtered)
    if total == 0:
        return "해당 조건의 판례 없음"

    dec_cnt  = Counter(m.get("decision", "불명") for m in filtered)
    tlaw_cnt = Counter(m.get("tax_type", "불명") for m in filtered)
    yr_cnt   = Counter(m.get("attr_yr", "불명") for m in filtered)

    lines = [f"=== 법원 판례 트렌드 (총 {total:,}건) ===\n"]

    lines.append("[결정유형 분포]")
    for k, v in dec_cnt.most_common():
        pct = round(v / total * 100, 1)
        lines.append(f"  {k}: {v}건 ({pct}%)")

    if not tax_type:
        lines.append("\n[세법 분류 (상위 10개)]")
        for k, v in tlaw_cnt.most_common(10):
            lines.append(f"  {k}: {v}건")

    lines.append("\n[기준연도 분포 (상위 10개)]")
    for yr in sorted(yr_cnt.keys(), reverse=True)[:10]:
        lines.append(f"  {yr}년: {yr_cnt[yr]}건")

    # 국패율 계산
    n_lose = dec_cnt.get("국패", 0) + dec_cnt.get("일부국패", 0)
    lose_pct = round(n_lose / total * 100, 1) if total else 0
    lines.append(f"\n납세자 승소(국패+일부국패): {n_lose}건 ({lose_pct}%)")

    return "\n".join(lines)


@tool
def find_winning_cases(fact_summary: str, tax_type: str = "") -> str:
    """
    사건 사실관계를 입력하면 유사한 납세자 승소(국패/일부국패) 판례를 찾아줍니다.

    Parameters
    ----------
    fact_summary : 사건 사실관계 요약 (예: '법인이 계열사에 저가 판매, 부당행위계산 부인 처분')
    tax_type     : 세법 (예: '법인세', '양도소득세')
    """
    try:
        col = _get_chroma_collection()
    except Exception as e:
        return f"벡터 DB 오류: {e}"

    # 국패·일부국패 위주로 검색
    winning_query = f"{fact_summary} 납세자 승소 국패 위법 취소"
    where = {"decision": {"$in": list(WINNING_DECISIONS)}}
    if tax_type:
        mapped = TAX_TYPE_MAP.get(tax_type.strip(), tax_type.strip())
        where = {"$and": [{"decision": {"$in": list(WINNING_DECISIONS)}},
                          {"tax_type": {"$eq": mapped}}]}

    try:
        results = col.query(query_texts=[winning_query], n_results=10, where=where)
    except Exception as e:
        # 필터 결과 없으면 필터 없이 재시도
        try:
            results = col.query(query_texts=[winning_query], n_results=10)
        except Exception as e2:
            return f"검색 오류: {e2}"

    docs  = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    if not docs:
        return f"'{fact_summary}' 관련 납세자 승소 판례를 찾지 못했습니다."

    winning = [(doc, meta) for doc, meta in zip(docs, metas)
               if meta.get("decision", "") in WINNING_DECISIONS]

    label = f"'{fact_summary[:50]}'"
    if not winning:
        winning = list(zip(docs[:5], metas[:5]))
        lines = [f"=== {label} — 유사 판례 (승소 사례 없어 전체 검색) ===\n"]
    else:
        lines = [f"=== {label} — 납세자 승소 유사 판례 {len(winning)}건 ===\n"]

    for i, (doc, meta) in enumerate(winning[:5], 1):
        lines.append(f"[{i}] {_format_brief(meta)}")
        snippet = "\n".join(doc.split("\n")[2:])[:200] if doc else ""
        if snippet:
            lines.append(f"    요지: {snippet}")
        lines.append(f"    → 전문: get_case_detail('{meta.get('doc_id', '')}')")
        lines.append("")

    lines += [
        "[전략 참고사항]",
        "  1. 과세처분의 법적 근거와 위 승소 판례의 사실관계 유사성 검토",
        "  2. 납세자 승소 핵심 논거 (위법사유, 절차 하자, 사실관계 불일치 등)",
        "  3. 경정청구 → 심판청구 → 행정소송 단계별 전략 분기",
    ]
    return "\n".join(lines)


@tool
def get_collection_stats() -> str:
    """법원 판례 벡터 DB 현황(총 건수, 세법별 분포)을 반환합니다."""
    try:
        col = _get_chroma_collection()
        total = col.count()
    except Exception as e:
        return f"DB 조회 오류: {e}"

    jsonl_lines = 0
    if JSONL_PATH.exists():
        with JSONL_PATH.open(encoding="utf-8", errors="replace") as f:
            jsonl_lines = sum(1 for l in f if l.strip())

    return (
        f"법원 판례 DB 현황 (taxlaw.nts.go.kr)\n"
        f"  벡터 임베딩: {total:,}건 (고유 DOC_ID 기준)\n"
        f"  원본 JSONL:  {jsonl_lines:,}건\n"
        f"  저장 경로:   {CHROMA_DIR}\n"
        f"\n세법·결정 분포는 analyze_trend() 도구를 사용하십시오."
    )


# ── 에이전트 ──────────────────────────────────────────────────────────────────

TOOLS = [
    search_court_cases,
    get_case_detail,
    analyze_trend,
    find_winning_cases,
    get_collection_stats,
]

SYSTEM_PROMPT = """당신은 세법 법원 판례 전문 AI 어시스턴트입니다.
국세청이 수집·분류한 법원 판례 32,000+건(taxlaw.nts.go.kr)을 기반으로
납세자 승소 전략, 판례 트렌드, 쟁점 분석을 제공합니다.

보유 데이터:
- 법원 판례 32,000+건 (대법원, 고등법원, 행정법원 등)
- 세법 분류: 법인세, 소득세, 부가가치세, 상속증여세, 양도소득세, 국세징수, 국제조세 등
- 결정유형: 국승(과세관청 승소) / 국패(납세자 승소) / 일부국패 / 각하

역할:
1. 유사 판례 검색 및 핵심 쟁점 요약
2. 세법·연도별 국승/국패 트렌드 분석
3. 납세자 승소 사례 발굴 → 소송·심판 전략 방향 제시
4. 판례 전문 조회 (98%에 전문 보유)

원칙:
- 구체적인 사건번호·요지를 근거로 설명
- "없다"고 단정하기 전에 여러 쿼리(세법 변형, 유사어)로 재검색
- 국패/일부국패 = 납세자 유리 → 전략 도출 우선
- 불확실한 법적 판단은 "추가 검토 필요" 명시
"""


class TaxlawPrecAgent:
    """세법 법원 판례 분석 에이전트."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0).bind_tools(TOOLS)
        self.tools_by_name = {t.name: t for t in TOOLS}
        self.messages = [SystemMessage(content=SYSTEM_PROMPT)]

    def _run_tool(self, tool_call: dict) -> str:
        name = tool_call["name"]
        args = tool_call.get("args", {})
        t = self.tools_by_name.get(name)
        if not t:
            return f"알 수 없는 도구: {name}"
        try:
            return t.invoke(args)
        except Exception as e:
            return f"도구 오류 ({name}): {e}"

    def ask(self, question: str, max_rounds: int = 6) -> str:
        from langchain_core.messages import AIMessage, ToolMessage

        self.messages.append(HumanMessage(content=question))

        for _ in range(max_rounds):
            response: AIMessage = self.llm.invoke(self.messages)
            self.messages.append(response)

            if not response.tool_calls:
                return response.content

            for tc in response.tool_calls:
                result = self._run_tool(tc)
                self.messages.append(
                    ToolMessage(content=result, tool_call_id=tc["id"])
                )

        return "최대 라운드 초과"

    def stream(self, question: str) -> Iterator[str]:
        from langchain_core.messages import AIMessage, ToolMessage

        self.messages.append(HumanMessage(content=question))

        for _ in range(6):
            response: AIMessage = self.llm.invoke(self.messages)
            self.messages.append(response)

            if not response.tool_calls:
                content = response.content
                for i in range(0, len(content), 50):
                    yield content[i:i+50]
                return

            for tc in response.tool_calls:
                result = self._run_tool(tc)
                self.messages.append(
                    ToolMessage(content=result, tool_call_id=tc["id"])
                )

        yield "최대 라운드 초과"

    def reset(self) -> None:
        self.messages = [SystemMessage(content=SYSTEM_PROMPT)]


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    ap = argparse.ArgumentParser(description="세법 법원 판례 에이전트")
    ap.add_argument("question", nargs="?", help="질문 (없으면 대화 모드)")
    args = ap.parse_args()

    agent = TaxlawPrecAgent()

    if args.question:
        print(agent.ask(args.question))
        return

    print("세법 법원 판례 에이전트 (종료: quit)\n")
    while True:
        try:
            q = input("질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("quit", "exit", "종료"):
            break
        if not q:
            continue
        print("\n" + agent.ask(q) + "\n")


if __name__ == "__main__":
    main()
