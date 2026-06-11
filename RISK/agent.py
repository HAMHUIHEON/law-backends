"""
법령 개정 리스크 에이전트

사용자 질문에 따라 법령 개정 분석 + 컨설팅 인사이트를 제공합니다.

사용:
    from RISK.agent import RiskAgent
    agent = RiskAgent()
    response = agent.ask("법인세법이 최근에 어떻게 바뀌었나요?")
    response = agent.ask("소득세법 개정으로 경정청구 기회가 있나요?")

    # 스트리밍
    for chunk in agent.stream("국세기본법 최신 개정 분석해줘"):
        print(chunk, end="", flush=True)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from utils.llm import get_llm, DEFAULT_MODEL
from RISK.consulting import (
    run_full_analysis,
    get_consulting_for_latest,
    run_cross_law_analysis,
    list_version_keys,
    load_law_json,
    LAW_SLUGS,
    KIND_FOLDER,
    CROSS_LAW_LINKS,
)
from RISK.run import make_version_context, load_risk_cache

ROOT = Path(__file__).parent.parent
LAW_DIR = ROOT / "law"


# ── 에이전트 도구 ────────────────────────────────────────────────────────────

@tool
def list_supported_laws() -> str:
    """지원하는 세법 목록과 보유 버전 수를 반환합니다."""
    lines = []
    for law_name, slug in LAW_SLUGS.items():
        parts = []
        for kind, folder in KIND_FOLDER.items():
            idx_path = LAW_DIR / slug / folder / "_version_index.json"
            if idx_path.exists():
                with idx_path.open(encoding="utf-8") as f:
                    cnt = len(json.load(f))
                parts.append(f"{kind}({cnt}버전)")
        lines.append(f"- {law_name}: {', '.join(parts)}" if parts else f"- {law_name}: 데이터 없음")
    return "\n".join(lines)


@tool
def get_law_versions(law_name: str, kind: str = "LAW") -> str:
    """
    특정 법령의 보유 버전 목록을 최신순으로 반환합니다.

    Parameters
    ----------
    law_name : 법령명 (예: 법인세법, 국세기본법)
    kind     : LAW | DECREE | RULE
    """
    try:
        versions = list_version_keys(law_name, kind)
    except Exception as e:
        return f"오류: {e}"

    if not versions:
        return f"{law_name}/{kind}: 버전 없음"

    lines = [f"{law_name}/{kind} 보유 버전 ({len(versions)}개, 최신순):"]
    for vk in versions[:20]:
        lines.append(f"  - {vk}")
    if len(versions) > 20:
        lines.append(f"  ... 외 {len(versions)-20}개")
    return "\n".join(lines)


@tool
def analyze_law_revision(law_name: str, kind: str = "LAW", version_key: str = "") -> str:
    """
    법령 개정 분석 + 컨설팅 인사이트를 실행합니다.
    version_key가 비어 있으면 최신 버전을 자동 선택합니다.

    Parameters
    ----------
    law_name    : 법령명 (예: 법인세법)
    kind        : LAW | DECREE | RULE
    version_key : YYYYMMDD_PPPPPPP 형식. 비우면 최신.
    """
    try:
        result = run_full_analysis(law_name, kind, version_key or None)
    except Exception as e:
        return f"분석 오류: {e}"

    consulting = result.consulting
    rev = result.revision

    lines = [
        f"=== {law_name} {kind} {result.version_key} 분석 결과 ===",
        f"",
        f"[전체 우선순위] {consulting.overall_priority}",
        f"",
        f"[종합 요약]",
        consulting.executive_summary,
        f"",
        f"[관측된 주요 변경 ({len(rev.observed_changes)}건)]",
    ]
    for ch in rev.observed_changes[:5]:
        lines.append(f"  - [{ch.change_type}] {ch.target.label}: {ch.description[:80]}...")

    lines += ["", f"[컨설팅 항목 ({len(consulting.items)}개)]"]
    for item in consulting.items:
        lines += [
            f"",
            f"  ▶ [{item.category}] {item.title}",
            f"    긴급도: {item.urgency} | 대상: {', '.join(item.target_clients)}",
            f"    내용: {item.description[:120]}",
            f"    권고: {item.action}",
            f"    근거: {', '.join(item.legal_basis)}",
        ]

    return "\n".join(lines)


@tool
def get_consulting_summary(law_name: str, kind: str = "LAW") -> str:
    """
    법령 최신 버전의 컨설팅 인사이트 요약만 빠르게 반환합니다.

    Parameters
    ----------
    law_name : 법령명
    kind     : LAW | DECREE | RULE
    """
    try:
        consulting = get_consulting_for_latest(law_name, kind)
    except Exception as e:
        return f"오류: {e}"

    lines = [
        f"{law_name}/{kind} 컨설팅 인사이트",
        f"우선순위: {consulting.overall_priority}",
        f"",
        consulting.executive_summary,
        f"",
        f"주요 항목:",
    ]
    for item in consulting.items:
        lines.append(f"  [{item.urgency}] {item.title}")
    return "\n".join(lines)


@tool
def search_articles_by_topic(query: str, n_results: int = 5) -> str:
    """
    벡터 DB에서 특정 주제와 관련된 법령 조문을 검색합니다.

    Parameters
    ----------
    query     : 검색 쿼리 (예: '이전가격 문서화 의무')
    n_results : 반환할 결과 수 (기본 5)
    """
    try:
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        import os

        ef = OpenAIEmbeddingFunction(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            model_name="text-embedding-3-small",
        )
        client = chromadb.PersistentClient(path=str(ROOT / "vector_db" / "chroma"))
        collection = client.get_collection("law_articles", embedding_function=ef)
        results = collection.query(query_texts=[query], n_results=n_results)

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        lines = [f"'{query}' 관련 조문 검색 결과:"]
        for i, (doc, meta) in enumerate(zip(docs, metas), 1):
            lines.append(
                f"\n[{i}] {meta.get('law_name', '')} {meta.get('kind', '')} "
                f"{meta.get('article_id', '')} {meta.get('title', '')}"
            )
            lines.append(f"    {doc[:200]}...")

        return "\n".join(lines)
    except Exception as e:
        return f"벡터 검색 오류: {e}"


@tool
def analyze_cross_law_impact(source_law: str) -> str:
    """
    외부 참조 법령(조세특례제한법, 상속세법, 관세법 등) 개정이
    연동 세법에 미치는 영향을 분석합니다.

    Parameters
    ----------
    source_law : 외부 법령명 (예: 조세특례제한법, 상속세 및 증여세법)
    """
    if source_law not in CROSS_LAW_LINKS:
        linked = list(CROSS_LAW_LINKS.keys())
        return f"'{source_law}'은 cross-law 분석 대상이 아닙니다.\n지원 대상: {linked}"

    try:
        out = run_cross_law_analysis(source_law)
    except Exception as e:
        return f"분석 오류: {e}"

    if not out:
        return f"{source_law}: cross-law 분석 결과 없음"

    linked = CROSS_LAW_LINKS.get(source_law, [])
    lines = [
        f"=== {source_law} → 세법 연동 영향 분석 ===",
        f"버전: {out.source_version_key}",
        f"연동 세법: {', '.join(linked)}",
        f"",
        f"[요약]",
        out.summary,
        f"",
        f"[연동 영향 항목 {len(out.items)}개]",
    ]
    for item in out.items:
        lines += [
            f"",
            f"  ▶ [{item.impact_type}] [{item.urgency}]",
            f"    외부 조문: {item.source_provision}",
            f"    영향 세법: {item.affected_tax_law} {item.affected_provision}",
            f"    내용: {item.description[:120]}",
            f"    대응: {item.consulting_point}",
        ]
    return "\n".join(lines)


@tool
def check_new_law_versions() -> str:
    """
    법제처 DRF API와 로컬 DB를 비교해 새로 공포된 법령 버전을 확인합니다.
    """
    from RISK.monitor import poll_all_laws
    new_by_law = poll_all_laws(kinds=["LAW"])

    if not new_by_law:
        return "현재 모든 법령이 최신 상태입니다."

    lines = [f"새 버전이 발견된 법령 {len(new_by_law)}개:"]
    for key, msts in new_by_law.items():
        lines.append(f"  - {key}: MST {msts}")
    return "\n".join(lines)


# ── 에이전트 클래스 ──────────────────────────────────────────────────────────

TOOLS = [
    list_supported_laws,
    get_law_versions,
    analyze_law_revision,
    get_consulting_summary,
    analyze_cross_law_impact,
    search_articles_by_topic,
    check_new_law_versions,
]

SYSTEM_PROMPT = """당신은 국세청 출신 세무사 AI 어시스턴트입니다. 한국 세법 전문가로서
법령 개정이 납세자에게 미치는 영향을 분석하고 컨설팅 방향을 제시합니다.

역할:
- 법령 개정 분석 (절세 기회, 경정청구 포인트, 새 의무 등)
- 고객군별 실무 대응 방향 제시
- 관련 조문 검색 및 해석 지원

사용 가능한 도구:
- list_supported_laws: 지원 법령 목록
- get_law_versions: 특정 법령 버전 이력
- analyze_law_revision: 법령 개정 분석 (시간 소요)
- get_consulting_summary: 컨설팅 인사이트 요약
- search_articles_by_topic: 관련 조문 검색
- check_new_law_versions: 새로 공포된 법령 감지

원칙:
- 구체적인 조문·부칙·별표를 근거로 설명할 것
- "검토 필요"가 아닌 구체적 행동을 권고할 것
- 불확실한 부분은 솔직하게 밝힐 것
"""


class RiskAgent:
    """법령 개정 리스크 + 컨설팅 에이전트."""

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

    def ask(self, question: str, max_rounds: int = 5) -> str:
        """에이전트에게 질문하고 최종 답변을 반환합니다."""
        from langchain_core.messages import AIMessage, ToolMessage

        self.messages.append(HumanMessage(content=question))

        for _ in range(max_rounds):
            response: AIMessage = self.llm.invoke(self.messages)
            self.messages.append(response)

            # 도구 호출 없으면 최종 답변
            if not response.tool_calls:
                return response.content

            # 도구 실행
            for tc in response.tool_calls:
                result = self._run_tool(tc)
                self.messages.append(
                    ToolMessage(content=result, tool_call_id=tc["id"])
                )

        return "응답 생성 중 최대 라운드 초과"

    def stream(self, question: str) -> Iterator[str]:
        """스트리밍 응답 (도구 호출 결과는 즉시 실행 후 최종 응답만 스트리밍)."""
        # 먼저 도구 라운드를 완료한 후 최종 답변만 스트리밍
        from langchain_core.messages import AIMessage, ToolMessage

        self.messages.append(HumanMessage(content=question))

        # 도구 라운드
        for _ in range(5):
            response: AIMessage = self.llm.invoke(self.messages)
            self.messages.append(response)

            if not response.tool_calls:
                # 최종 응답 — 스트리밍 (간단히 청크 단위)
                content = response.content
                chunk_size = 50
                for i in range(0, len(content), chunk_size):
                    yield content[i : i + chunk_size]
                return

            for tc in response.tool_calls:
                result = self._run_tool(tc)
                self.messages.append(
                    ToolMessage(content=result, tool_call_id=tc["id"])
                )

        yield "응답 생성 중 최대 라운드 초과"

    def reset(self) -> None:
        """대화 이력 초기화."""
        self.messages = [SystemMessage(content=SYSTEM_PROMPT)]


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="법령 개정 리스크 에이전트")
    ap.add_argument("question", nargs="?", help="질문 (없으면 대화 모드)")
    args = ap.parse_args()

    agent = RiskAgent()

    if args.question:
        print(agent.ask(args.question))
        return

    # 대화 모드
    print("법령 개정 리스크 에이전트 (종료: quit)\n")
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
