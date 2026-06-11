"""
조세심판원 재결례 에이전트

사용자 질의에 따라 재결례 검색·분석·전략을 제공합니다.

사용:
    from agents.taxtr_agent import TaxtrAgent

    agent = TaxtrAgent()
    response = agent.ask("이전가격 관련 최근 3년 심판 결정 패턴이 어떻게 되나요?")
    response = agent.ask("법인세 부당행위계산 부인 관련해서 납세자가 이긴 사례 있나요?")
    response = agent.ask("우리 회사가 이전가격으로 과세처분 받았는데 어떻게 대응해야 하나요?")
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator, Optional

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from utils.llm import get_llm, DEFAULT_MODEL
ROOT      = Path(__file__).parent.parent
CASES_DIR = ROOT / "cases" / "taxtr"
CHROMA_DIR = ROOT / "vector_db" / "chroma"

# Chroma 저장 값 매핑 (사용자 입력 → DB 저장 코드)
TAX_TYPE_MAP: dict[str, str] = {
    "법인세": "법인", "법인": "법인",
    "부가가치세": "부가", "부가": "부가",
    "소득세": "종합소득", "종합소득세": "종합소득", "종합소득": "종합소득",
    "양도소득세": "양도", "양도": "양도",
    "취득세": "취득", "취득": "취득",
    "증여세": "증여", "증여": "증여",
    "상속세": "상속", "상속": "상속",
    "종합부동산세": "종합부동산", "종합부동산": "종합부동산",
    "관세": "관세",
    "근로소득세": "근로소득", "근로소득": "근로소득",
    "지방소득세": "지방소득", "지방소득": "지방소득",
}
DECISION_MAP: dict[str, str] = {
    "취소": "취소", "인용": "취소", "납세자 승소": "취소", "승소": "취소",
    "기각": "기각", "패소": "기각",
    "경정": "경정",
    "각하": "각하",
    "재조사": "재조사",
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
    return client.get_collection("taxtr_cases", embedding_function=ef)


def _load_case_file(dem_no: str) -> Optional[dict]:
    """로컬 JSON 파일에서 재결례 전문 로드."""
    p = CASES_DIR / f"{dem_no}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _format_case_brief(meta: dict, doc: str = "") -> str:
    """재결례 한 줄 요약."""
    parts = []
    if meta.get("case_no"):
        parts.append(f"[{meta['case_no']}]")
    if meta.get("decision_date"):
        parts.append(meta["decision_date"])
    if meta.get("tax_type"):
        parts.append(f"세목:{meta['tax_type']}")
    if meta.get("decision"):
        parts.append(f"결정:{meta['decision']}")
    header = " | ".join(parts)
    title = meta.get("title", "")
    return f"{header}\n  {title}" if title else header


# ── 에이전트 도구 ─────────────────────────────────────────────────────────────

@tool
def search_cases(
    query: str,
    tax_type: str = "",
    decision: str = "",
    n_results: int = 8,
) -> str:
    """
    재결례 벡터 DB에서 유사 사례를 검색합니다.

    Parameters
    ----------
    query     : 검색 질의 (예: '이전가격 정상가격 산출 방법 부인')
    tax_type  : 세목 필터 (예: '법인세', '부가가치세', '소득세') — 빈 문자열이면 전체
    decision  : 결정유형 필터 (예: '취소', '기각', '인용') — 빈 문자열이면 전체
    n_results : 반환 건수 (기본 8)
    """
    try:
        col = _get_chroma_collection()
    except Exception as e:
        return f"벡터 DB 연결 오류: {e}"

    # where 조건 구성 — Chroma는 $eq/$in/$nin/$and/$or 지원
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

    docs   = results.get("documents", [[]])[0]
    metas  = results.get("metadatas", [[]])[0]
    dists  = results.get("distances", [[]])[0]

    if not docs:
        return "검색 결과 없음"

    lines = [f"'{query}' 관련 재결례 {len(docs)}건:\n"]
    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), 1):
        similarity = round(1 - dist, 3)
        lines.append(f"[{i}] 유사도 {similarity} | {_format_case_brief(meta)}")
        # 요지 일부
        snippet = doc.split("\n")[-1][:150] if doc else ""
        if snippet:
            lines.append(f"    요지: {snippet}")
        lines.append("")

    return "\n".join(lines)


@tool
def get_case_detail(dem_no: str) -> str:
    """
    특정 재결례의 전문을 조회합니다.

    Parameters
    ----------
    dem_no : 재결례 dem_no (숫자 문자열, 예: '210543')
    """
    case = _load_case_file(dem_no.strip())
    if not case:
        return f"dem_no={dem_no} 재결례를 찾을 수 없습니다."

    lines = [
        f"=== 재결례 상세 ===",
        f"청구번호: {case.get('case_no', '')}",
        f"결정일자: {case.get('decision_date', '')}",
        f"세목: {case.get('tax_type', '')}",
        f"결정유형: {case.get('decision', '')}",
        f"",
        f"[제목]",
        case.get("title", ""),
        f"",
        f"[결정요지]",
        case.get("summary", ""),
        f"",
        f"[관련법령]",
        case.get("related_laws", ""),
    ]
    return "\n".join(lines)


@tool
def analyze_trend(tax_type: str = "", year: str = "") -> str:
    """
    재결례 결정 유형 트렌드를 분석합니다.

    Parameters
    ----------
    tax_type : 세목 필터 (예: '법인세') — 빈 문자열이면 전체
    year     : 연도 필터 4자리 (예: '2024') — 빈 문자열이면 전체
    """
    if not CASES_DIR.exists():
        return "재결례 폴더 없음"

    from collections import Counter

    total = 0
    decision_cnt: Counter = Counter()
    tax_cnt: Counter = Counter()
    year_cnt: Counter = Counter()

    for fp in CASES_DIR.glob("*.json"):
        try:
            case = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue

        # 필터 적용
        if tax_type and tax_type not in case.get("tax_type", ""):
            continue
        d_date = case.get("decision_date", "")
        if year and not d_date.startswith(year):
            continue

        total += 1
        decision_cnt[case.get("decision", "불명")] += 1
        tax_cnt[case.get("tax_type", "불명")] += 1
        y = d_date[:4] if d_date else "불명"
        year_cnt[y] += 1

    if total == 0:
        return "해당 조건의 재결례 없음"

    lines = [f"=== 트렌드 분석 (총 {total}건) ===\n"]

    lines.append("[결정유형 분포]")
    for k, v in decision_cnt.most_common():
        pct = round(v / total * 100, 1)
        lines.append(f"  {k}: {v}건 ({pct}%)")

    if not tax_type:
        lines.append("\n[세목 분포 (상위 10개)]")
        for k, v in tax_cnt.most_common(10):
            lines.append(f"  {k}: {v}건")

    if not year:
        lines.append("\n[연도별 추이]")
        for y in sorted(year_cnt.keys()):
            lines.append(f"  {y}: {year_cnt[y]}건")

    return "\n".join(lines)


@tool
def find_winning_strategy(fact_summary: str, tax_type: str = "") -> str:
    """
    의뢰인 사건 개요를 입력하면 유사한 납세자 승소 사례와 전략을 찾아줍니다.

    Parameters
    ----------
    fact_summary : 사건 사실관계 요약 (예: '다국적기업 이전가격 정상가격 부인 처분, 비교대상거래 없음 주장')
    tax_type     : 세목 (예: '법인세')
    """
    # 1단계: 유사 사례 검색 (취소·인용 위주)
    try:
        col = _get_chroma_collection()
    except Exception as e:
        return f"벡터 DB 오류: {e}"

    winning_query = f"{fact_summary} 납세자 승소 취소 인용"
    try:
        results = col.query(query_texts=[winning_query], n_results=10)
    except Exception as e:
        return f"검색 오류: {e}"

    docs  = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    # 취소·인용 결정만 필터
    winning = [
        (doc, meta) for doc, meta in zip(docs, metas)
        if meta.get("decision", "") in ("취소", "인용", "일부취소", "일부인용")
    ]

    if not winning:
        return f"'{fact_summary}' 관련 납세자 승소 사례를 찾지 못했습니다.\n일반 유사 사례로 대체합니다.\n\n" + \
               search_cases.invoke({"query": fact_summary, "tax_type": tax_type})

    lines = [
        f"=== '{fact_summary[:50]}' 관련 납세자 승소 사례 {len(winning)}건 ===\n",
        "[참고 사례]",
    ]
    for i, (doc, meta) in enumerate(winning[:5], 1):
        lines.append(f"\n[{i}] {_format_case_brief(meta)}")
        snippet = doc.split("\n")[-1][:200] if doc else ""
        if snippet:
            lines.append(f"    요지: {snippet}")
        lines.append(f"    → 전문 조회: get_case_detail('{meta.get('dem_no', '')}')")

    lines += [
        "",
        "[전략 참고사항]",
        "위 사례를 바탕으로 다음을 검토하십시오:",
        "  1. 과세 처분의 법적 근거와 사실관계가 위 승소 사례와 어떻게 유사한지",
        "  2. 납세자가 승소한 핵심 논거 (벡터 유사도 기준 상위 사례 먼저 검토)",
        "  3. 경정청구 / 심판청구 / 행정소송 단계별 전략 분기",
    ]
    return "\n".join(lines)


@tool
def get_collection_stats() -> str:
    """재결례 벡터 DB의 현황(총 건수, 세목 분포 등)을 반환합니다."""
    try:
        col = _get_chroma_collection()
        total = col.count()
    except Exception as e:
        return f"DB 조회 오류: {e}"

    file_count = len(list(CASES_DIR.glob("*.json"))) if CASES_DIR.exists() else 0

    return (
        f"재결례 DB 현황\n"
        f"  벡터 임베딩: {total}건\n"
        f"  로컬 JSON:   {file_count}건\n"
        f"  저장 경로:   {CHROMA_DIR}\n"
        f"\n세목별 분포는 analyze_trend() 도구를 사용하십시오."
    )


# ── 에이전트 ──────────────────────────────────────────────────────────────────

TOOLS = [
    search_cases,
    get_case_detail,
    analyze_trend,
    find_winning_strategy,
    get_collection_stats,
]

SYSTEM_PROMPT = """당신은 조세심판원 재결례 전문 AI 어시스턴트입니다.
국세청 출신 세무사 관점에서 재결례를 분석하고 실무 전략을 제시합니다.

보유 데이터:
- 조세심판원 재결례 (2021~2026년, 약 15,000건)
- 세목: 법인세, 소득세, 부가가치세, 상속세, 증여세, 국제조세 등 전체

역할:
1. 유사 재결례 검색 및 요약
2. 세목·연도별 결정 트렌드 분석
3. 의뢰인 사건과 유사한 납세자 승소 사례 발굴
4. 경정청구·심판청구·소송 전략 방향 제시

원칙:
- 구체적인 청구번호·결정요지를 근거로 설명할 것
- "관련 사례가 없다"고 단정하기 전에 여러 쿼리로 검색할 것
- 전략은 재결례 패턴 기반으로 — 막연한 조언 금지
- 불확실한 부분은 "추가 검토 필요" 명시
"""


class TaxtrAgent:
    """조세심판원 재결례 분석 에이전트."""

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
        """질문하고 최종 답변을 반환합니다."""
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
        """스트리밍 응답."""
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
        """대화 이력 초기화."""
        self.messages = [SystemMessage(content=SYSTEM_PROMPT)]


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    ap = argparse.ArgumentParser(description="조세심판원 재결례 에이전트")
    ap.add_argument("question", nargs="?", help="질문 (없으면 대화 모드)")
    args = ap.parse_args()

    agent = TaxtrAgent()

    if args.question:
        print(agent.ask(args.question))
        return

    print("조세심판원 재결례 에이전트 (종료: quit)\n")
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
