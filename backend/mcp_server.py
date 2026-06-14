# mcp_server.py
# Lapis Nexus MCP 서버
# Claude Desktop에 연결하면 세무사/회계사가 바로 쓸 수 있음
#
# 사용법:
#   pip install mcp
#   python mcp_server.py
#
# Claude Desktop 설정 (claude_desktop_config.json):
#   {
#     "mcpServers": {
#       "lapis-nexus": {
#         "command": "python",
#         "args": ["/절대경로/backend/mcp_server.py"]
#       }
#     }
#   }

import sys
import json
import concurrent.futures
from pathlib import Path

# backend 폴더를 Python path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("lapis-nexus")


# ────────────────────────────────────────────────────────────────
# Tool 1: 판례 분석 실행
# ────────────────────────────────────────────────────────────────

@mcp.tool()
def analyze_case(pdf_path: str, case_id: str = "") -> str:  # noqa: E302
    """
    판결문 PDF를 분석하여 논증 구조를 추출합니다.
    이미 분석된 판례는 캐시에서 즉시 반환합니다 (재분석 없음).

    Args:
        pdf_path: 판결문 PDF 파일의 절대 경로
        case_id:  판례 번호 (예: 2022구합7106). 비워두면 파일명에서 자동 추출.

    Returns:
        분석 결과 JSON 문자열
    """
    from pathlib import Path as P
    from case_cache import save_analysis, load_analysis

    # case_id 결정
    if not case_id:
        case_id = P(pdf_path).stem

    # ① 캐시 확인
    cached = load_analysis(case_id)
    if cached:
        cached["_source"] = "cache"
        return json.dumps(cached, ensure_ascii=False, indent=2)

    # ② 파일 존재 확인
    if not P(pdf_path).exists():
        return json.dumps({"error": f"파일을 찾을 수 없습니다: {pdf_path}"}, ensure_ascii=False)

    # ③ 파이프라인 실행 (최대 15분 타임아웃)
    try:
        from bravo.full_pipeline import run_full_pipeline
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as exe:
            future = exe.submit(run_full_pipeline, pdf_path)
            try:
                result = future.result(timeout=900)
            except concurrent.futures.TimeoutError:
                return json.dumps({
                    "error": "파이프라인 실행 시간 초과 (15분). 캐시된 단계까지는 저장되었습니다. 재실행하면 이어서 처리됩니다."
                }, ensure_ascii=False)

        # Pydantic 객체가 섞여있을 수 있어서 직렬화 처리
        def _to_dict(obj):
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if isinstance(obj, dict):
                return {k: _to_dict(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_to_dict(i) for i in obj]
            return obj

        result_dict = _to_dict(result)
        result_dict["case_id"] = case_id

        # ④ 캐시에 저장
        save_analysis(case_id, result_dict)

        result_dict["_source"] = "pipeline"
        return json.dumps(result_dict, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 2: 캐시에서 분석 결과 조회
# ────────────────────────────────────────────────────────────────

@mcp.tool()
def get_case_analysis(case_id: str) -> str:
    """
    이미 분석된 판례를 캐시에서 즉시 조회합니다.
    analyze_case를 먼저 실행해야 결과가 있습니다.

    Args:
        case_id: 판례 번호 (예: 2022구합7106)

    Returns:
        분석 결과 JSON 문자열. 없으면 오류 메시지.
    """
    from case_cache import load_analysis
    result = load_analysis(case_id)
    if result is None:
        return json.dumps({
            "error": f"캐시에 없습니다: {case_id}. analyze_case를 먼저 실행하세요."
        }, ensure_ascii=False)
    result["_source"] = "cache"
    return json.dumps(result, ensure_ascii=False, indent=2)


# ────────────────────────────────────────────────────────────────
# Tool 3: 분석된 판례 목록
# ────────────────────────────────────────────────────────────────

@mcp.tool()
def list_analyzed_cases() -> str:
    """
    지금까지 분석하여 캐시에 저장된 판례 목록을 반환합니다.

    Returns:
        판례 번호, 분석 일시 목록
    """
    from case_cache import list_cases
    cases = list_cases()
    if not cases:
        return "아직 분석된 판례가 없습니다. analyze_case로 판례를 분석해보세요."
    return json.dumps(cases, ensure_ascii=False, indent=2)


# ────────────────────────────────────────────────────────────────
# Tool 4: 쟁점 요약 (세무사/회계사용 실무 뷰)
# ────────────────────────────────────────────────────────────────

@mcp.tool()
def get_issue_summary(case_id: str) -> str:
    """
    판례의 핵심 쟁점과 법원 판단 논리를 실무자가 읽기 쉽게 요약합니다.
    경정청구, 세무조사 대응 자문 시 빠른 파악에 유용합니다.

    Args:
        case_id: 판례 번호

    Returns:
        쟁점별 요약 텍스트
    """
    from case_cache import load_analysis
    result = load_analysis(case_id)
    if result is None:
        return f"캐시에 없습니다: {case_id}. analyze_case를 먼저 실행하세요."

    lines = [f"# 판례 {case_id} — 쟁점 요약\n"]

    # 내러티브
    narrative = result.get("narrative", {})
    if narrative.get("fact_summary"):
        lines.append(f"## 사실관계\n{narrative['fact_summary']}\n")

    if narrative.get("core_conflicts"):
        lines.append("## 핵심 쟁점")
        for i, c in enumerate(narrative["core_conflicts"], 1):
            lines.append(f"{i}. {c}")
        lines.append("")

    # 쟁점별 논증 구조
    issue_logic = result.get("issue_logic", {})
    chains = issue_logic.get("issue_logic_chains", [])
    if chains:
        lines.append("## 쟁점별 법원 판단")
        for ch in chains:
            lines.append(f"\n### {ch.get('issue', '')}")
            if ch.get("rule"):
                lines.append(f"**적용 법리**: {ch['rule']}")
            if ch.get("application"):
                lines.append(f"**적용**: {ch['application']}")
            if ch.get("mini_conclusion"):
                lines.append(f"**소결**: {ch['mini_conclusion']}")
            # 인용 법령
            citations = ch.get("citations", [])
            if citations:
                lines.append(f"**관련 법령/판례**: {', '.join(citations)}")

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────
# Tool 5: 유사 쟁점 판례 검색 (벡터 의미 유사도)
# ────────────────────────────────────────────────────────────────

@mcp.tool()
def search_similar_issues(query: str, top_k: int = 5) -> str:
    """
    자연어 쿼리와 의미적으로 유사한 쟁점을 가진 판례를 검색합니다.
    Neo4j 벡터 인덱스(text-embedding-3-small)를 사용한 시맨틱 검색입니다.

    Args:
        query: 검색할 쟁점 (예: "특수관계자 자산 저가양도 부당행위계산 부인")
        top_k: 반환할 판례 수 (기본값 5, 최대 20)

    Returns:
        유사 판례 목록 — case_number, court, issue, rule, mini_conclusion, 유사도 점수
    """
    try:
        from db.graph_search import LegalGraphSearch
        searcher = LegalGraphSearch()
        results = searcher.search_similar_issues(query, top_k=min(top_k, 20))
        searcher.close()
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 6: 법령 기반 판례 탐색 (그래프 트래버설)
# ────────────────────────────────────────────────────────────────

@mcp.tool()
def get_statute_cases(statute_name: str) -> str:
    """
    특정 법령이 핵심 근거로 인용된 판례와 쟁점을 시계열순으로 반환합니다.
    판례 법리 변천사 파악에 유용합니다.

    Args:
        statute_name: 법령명 (예: "국세기본법", "법인세법", "부가가치세법")

    Returns:
        해당 법령 관련 판례 목록 — 시계열순, 쟁점·법리·결론 포함
    """
    try:
        from db.graph_search import LegalGraphSearch
        searcher = LegalGraphSearch()
        results = searcher.get_statute_cases(statute_name)
        searcher.close()
        if not results:
            return json.dumps(
                {"message": f"'{statute_name}' 관련 판례가 없습니다."},
                ensure_ascii=False,
            )
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 7: 승소 패턴 분석 (그래프 + 벡터 하이브리드)
# ────────────────────────────────────────────────────────────────

@mcp.tool()
def analyze_winning_patterns(query: str, top_k: int = 10) -> str:
    """
    유사 쟁점 판례들을 검색하고, 각 판례의 결론·적용 법리·인용 법령을
    종합하여 승소/패소 패턴 분석 데이터를 반환합니다.
    경정청구·세무조사 대응 전략 수립에 활용하세요.

    Args:
        query: 분석할 쟁점 (예: "해외 특수관계자 이전가격 정상가격 산출")
        top_k: 분석에 사용할 유사 판례 수 (기본값 10)

    Returns:
        유사 판례 + 판례별 결론 + 가장 많이 인용된 법령 통계
    """
    try:
        from db.graph_search import LegalGraphSearch
        searcher = LegalGraphSearch()
        result = searcher.analyze_winning_patterns(query, top_k=min(top_k, 20))
        searcher.close()
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 8: InsightAgent — 판례 심층 분석 (LangGraph 5단계)
# ────────────────────────────────────────────────────────────────

_insight_agent = None

def _get_insight_agent():
    global _insight_agent
    if _insight_agent is None:
        from agents.insight_agent import InsightAgent
        _insight_agent = InsightAgent()
    return _insight_agent


@mcp.tool()
def run_insight_agent(query: str, case_id: str = "") -> str:
    """
    InsightAgent: 판례 DB + 법령 데이터를 5단계 LangGraph 파이프라인으로 분석합니다.
    Planner → Executor → Insight → Critic → Reporter 순으로 실행됩니다.

    Args:
        query: 분석할 쟁점 또는 질문 (예: "특수관계자 저가양도 부당행위계산 부인 요건")
        case_id: 판례 번호를 지정하면 해당 판례를 원문 기반으로 심층 분석 (예: "2022구합7106")

    Returns:
        실무 보고서 — 핵심 판례, 승소 전략, 리스크, 법령 근거 포함
    """
    try:
        agent = _get_insight_agent()
        result = agent.run(query=query, case_id=case_id if case_id else None)
        report = result.get("final_report", "")
        steps = result.get("steps", [])
        insight = result.get("insight")

        output_parts = [report]
        if steps:
            output_parts.append(f"\n---\n실행 단계: {', '.join(steps)}")
        if insight:
            output_parts.append(f"\n---\n심층 분석 (ExportC):\n{json.dumps(insight, ensure_ascii=False, indent=2)}")

        return "\n".join(output_parts)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 9: SupervisorAgent — 판례 + ITCL 법령 교차 분석
# ────────────────────────────────────────────────────────────────

_supervisor_agent = None

def _get_supervisor_agent():
    global _supervisor_agent
    if _supervisor_agent is None:
        from agents.multi_agent import SupervisorAgent
        _supervisor_agent = SupervisorAgent()
    return _supervisor_agent


@mcp.tool()
def run_supervisor_agent(query: str) -> str:
    """
    SupervisorAgent (종합 리서치): 6개 소스를 동시에 탐색해 통합 보고서를 생성합니다.
    - Neo4j 판례 DB (국제조세 구조화 판례)
    - Chroma law_articles: 14개 세법 조문 6,687건
    - Chroma taxlaw_prec: NTS 법원 판례 32,628건
    - Chroma taxtr_cases: 조세심판 재결례 2,463건
    - issue_index: 사전 분석 쟁점 벡터 1,021건
    - Chroma pdf_court_cases: PDF 원본 판결문 560건
    이전가격(ITCL) 관련 쿼리는 국조법 조문·판례를 우선 탐색합니다.

    Args:
        query: 분석할 질문 (예: "이전가격 과소신고 관련 판례와 세법 법령 종합 분석")

    Returns:
        통합 보고서 — 판례 컨텍스트 + 법령 조문 + 재결례 + PDF 판례 + 쟁점 캐시
    """
    try:
        agent = _get_supervisor_agent()
        result = agent.run(query=query)
        report = result.get("final_report", "")
        case_ctx = result.get("case_context")
        law_ctx = result.get("law_articles_context")
        prec_ctx = result.get("taxlaw_prec_context")
        taxtr_ctx = result.get("taxtr_context")
        pdf_ctx = result.get("pdf_cases_context")
        issue_ctx = result.get("issue_cache_context")

        output_parts = [report]
        if case_ctx:
            output_parts.append(f"\n---\n판례 컨텍스트:\n{json.dumps(case_ctx, ensure_ascii=False, indent=2)}")
        if law_ctx:
            output_parts.append(f"\n---\n법령 조문:\n{json.dumps(law_ctx, ensure_ascii=False, indent=2)}")
        if prec_ctx:
            output_parts.append(f"\n---\nNTS 법원 판례:\n{json.dumps(prec_ctx, ensure_ascii=False, indent=2)}")
        if taxtr_ctx:
            output_parts.append(f"\n---\n조세심판 재결례:\n{json.dumps(taxtr_ctx, ensure_ascii=False, indent=2)}")
        if pdf_ctx:
            output_parts.append(f"\n---\nPDF 판결문:\n{json.dumps(pdf_ctx, ensure_ascii=False, indent=2)}")
        if issue_ctx:
            output_parts.append(f"\n---\n구조화 쟁점 캐시:\n{json.dumps(issue_ctx, ensure_ascii=False, indent=2)}")

        return "\n".join(output_parts)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 10: StrategyAgent — 의뢰인 사건 전략 권고
# ────────────────────────────────────────────────────────────────

_strategy_agent = None

def _get_strategy_agent():
    global _strategy_agent
    if _strategy_agent is None:
        from agents.strategy_agent import StrategyAgent
        _strategy_agent = StrategyAgent()
    return _strategy_agent


@mcp.tool()
def run_strategy_agent(client_summary: str) -> str:
    """
    의뢰인 사건 전략 에이전트: 사건 요약을 입력하면 유사 판례를 분석하고
    경정청구 / 조세심판 / 행정소송 중 최적 전략을 권고합니다.
    세무사·변호사가 의뢰인 상담 시 즉시 활용할 수 있습니다.

    Args:
        client_summary: 의뢰인 사건 요약 (세목, 처분 내용, 핵심 사실관계 포함)

    Returns:
        전략 보고서 — 유사 판례 분석, 쟁점별 승산, 절차별 강약점, 최종 권고
    """
    try:
        agent = _get_strategy_agent()
        result = agent.run(client_summary=client_summary)
        return result.get("final_report", "보고서 생성에 실패했습니다.")
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 11: CompareAgent — 두 판례 비교 분석
# ────────────────────────────────────────────────────────────────

_compare_agent = None

def _get_compare_agent():
    global _compare_agent
    if _compare_agent is None:
        from agents.compare_agent import CompareAgent
        _compare_agent = CompareAgent()
    return _compare_agent


@mcp.tool()
def run_compare_agent(case_ids: str) -> str:
    """
    판례 비교 에이전트: 2개 이상 판례(최대 10개)의 쟁점·법리·결론을 비교합니다.
    어떤 사실관계 차이가 서로 다른 판결을 낳았는지 분석합니다.
    분석하려는 판례는 analyze_case로 먼저 처리되어 있어야 합니다.

    Args:
        case_ids: 판례 번호들을 쉼표로 구분 (예: "2022구합7106,2009두23945,2015두1243")

    Returns:
        비교 보고서 — 공통 쟁점 분석, 결론 가른 사실관계 차이, 승소 패턴, 실무 시사점
    """
    try:
        ids = [c.strip() for c in case_ids.split(",") if c.strip()]
        if len(ids) < 2:
            return "판례 번호를 쉼표로 구분해 2개 이상 입력하세요. 예: '2022구합7106,2009두23945'"
        agent = _get_compare_agent()
        result = agent.run(case_ids=ids)
        return result.get("final_report", "보고서 생성에 실패했습니다.")
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 12: TrendAgent — 판례 트렌드 분석
# ────────────────────────────────────────────────────────────────

_trend_agent = None

def _get_trend_agent():
    global _trend_agent
    if _trend_agent is None:
        from agents.trend_agent import TrendAgent
        _trend_agent = TrendAgent()
    return _trend_agent


@mcp.tool()
def run_trend_agent(query: str, start_year: int = 2000, end_year: int = 2030) -> str:
    """
    판례 트렌드 에이전트: 쟁점 키워드로 연도별 납세자 승소율을 집계하고
    법리 변천사와 최근 트렌드를 분석합니다.

    Args:
        query: 분석할 쟁점 (예: "부당행위계산 부인", "이전가격 정상가격")
        start_year: 분석 시작 연도 (기본값: 2000)
        end_year: 분석 종료 연도 (기본값: 2030)

    Returns:
        트렌드 보고서 — 연도별 승소율, 법리 변천사, 최근 흐름 진단
    """
    try:
        agent = _get_trend_agent()
        result = agent.run(query=query, start_year=start_year, end_year=end_year)
        report = result.get("final_report", "")
        data = result.get("trend_data") or {}
        year_stats = data.get("year_stats") or {}
        if year_stats:
            stats_lines = ["\n---\n연도별 통계:"]
            for year, s in year_stats.items():
                stats_lines.append(f"  {year}: {s['total']}건 / 납세자 승소 {s['taxpayer_win']}건 ({s['win_rate']}%)")
            return report + "\n".join(stats_lines)
        return report
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 13: RebuttalAgent — 반론 초안 생성
# ────────────────────────────────────────────────────────────────

_rebuttal_agent = None

def _get_rebuttal_agent():
    global _rebuttal_agent
    if _rebuttal_agent is None:
        from agents.rebuttal_agent import RebuttalAgent
        _rebuttal_agent = RebuttalAgent()
    return _rebuttal_agent


@mcp.tool()
def run_rebuttal_agent(disposition_text: str) -> str:
    """
    반론 초안 생성 에이전트: 과세처분 이유서를 입력하면
    납세자 승소 판례를 기반으로 이의신청서·심판청구서 반론 초안을 생성합니다.
    Self-Reflection으로 품질을 자동 검증합니다.

    Args:
        disposition_text: 과세처분 이유서 전문 또는 핵심 내용

    Returns:
        반론 초안 — 쟁점별 반론, 판례 근거, 청구취지
    """
    try:
        agent = _get_rebuttal_agent()
        result = agent.run(disposition_text=disposition_text)
        return result.get("final_report", "초안 생성에 실패했습니다.")
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 14: ITCLAgent — 이전가격·국제조세 전문 분석
# ────────────────────────────────────────────────────────────────

_itcl_agent = None

def _get_itcl_agent():
    global _itcl_agent
    if _itcl_agent is None:
        from agents.itcl_agent import ITCLAgent
        _itcl_agent = ITCLAgent()
    return _itcl_agent


@mcp.tool()
def run_itcl_agent(query: str) -> str:
    """
    이전가격·국제조세 전문 에이전트: 특수관계자 거래 정보를 입력하면
    정상가격 산출 방법 검토, 관련 판례 분석, 조세 리스크 평가를 제공합니다.
    국제조세조정에 관한 법률 조문 데이터와 연계됩니다.

    Args:
        query: 거래 내용 또는 분석 질의 (예: "A사가 해외 특수관계법인에 원가에 공급, 정상가격 여부")

    Returns:
        이전가격 분석 보고서 — 산출 방법 검토, 판례 시사점, 리스크 평가, 권고
    """
    try:
        agent = _get_itcl_agent()
        result = agent.run(query=query)
        return result.get("final_report", "보고서 생성에 실패했습니다.")
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 15: RiskAgent — 법령 개정 리스크 분석
# ────────────────────────────────────────────────────────────────

_risk_agent = None

def _get_risk_agent():
    global _risk_agent
    if _risk_agent is None:
        from agents.risk_agent import RiskAgent
        _risk_agent = RiskAgent()
    return _risk_agent


@mcp.tool()
def run_risk_agent(statute_name: str, revision_summary: str, effective_date: str = "") -> str:
    """
    법령 개정 리스크 에이전트: 법령 개정 내용을 입력하면
    해당 법령을 인용한 기존 판례들이 개정 후에도 유효한지 재평가하고
    리스크 등급별(🔴🟡🟢) 보고서를 생성합니다.

    Args:
        statute_name: 개정 법령명 (예: "법인세법", "국세기본법")
        revision_summary: 개정 내용 요약
        effective_date: 시행일 (예: "2025-01-01", 생략 가능)

    Returns:
        리스크 보고서 — 영향 판례 분류, 핵심 리스크, 실무 대응 방안
    """
    try:
        agent = _get_risk_agent()
        result = agent.run(
            statute_name=statute_name,
            revision_summary=revision_summary,
            effective_date=effective_date,
        )
        return result.get("final_report", "보고서 생성에 실패했습니다.")
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 16: TaxlawPrecAgent — NTS 법원 판례 검색 (32,628건)
# ────────────────────────────────────────────────────────────────

_taxlaw_prec_agent = None

def _get_taxlaw_prec_agent():
    global _taxlaw_prec_agent
    if _taxlaw_prec_agent is None:
        from agents.taxlaw_prec_agent import TaxlawPrecAgent
        _taxlaw_prec_agent = TaxlawPrecAgent()
    return _taxlaw_prec_agent


@mcp.tool()
def run_taxlaw_prec_agent(question: str) -> str:
    """
    NTS 법원 판례 에이전트: 국세청 taxlaw.nts.go.kr에서 수집한 법원 판례
    32,628건을 벡터 검색으로 분석합니다. 국승/국패 패턴 파악에 유용합니다.

    Args:
        question: 분석할 질문 (예: "이전가격 정상가격 산정 관련 국패 판례 패턴은?")

    Returns:
        GPT 분석 보고서 — 유사 판례 요약, 국승/국패 패턴, 시사점
    """
    try:
        agent = _get_taxlaw_prec_agent()
        result = agent.ask(question)
        return result
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# Tool 17: TaxtrAgent — 조세심판 재결례 검색 (2,463건)
# ────────────────────────────────────────────────────────────────

_taxtr_agent = None

def _get_taxtr_agent():
    global _taxtr_agent
    if _taxtr_agent is None:
        from agents.taxtr_agent import TaxtrAgent
        _taxtr_agent = TaxtrAgent()
    return _taxtr_agent


@mcp.tool()
def run_taxtr_agent(question: str) -> str:
    """
    조세심판 재결례 에이전트: 조세심판원 재결례 2,463건을 벡터 검색으로 분석합니다.
    이의신청·심판청구 전략 수립 시 참고 재결례를 빠르게 파악할 수 있습니다.

    Args:
        question: 분석할 질문 (예: "부당행위계산부인 인용 재결례 특징은?")

    Returns:
        GPT 분석 보고서 — 유사 재결례 요약, 인용/기각 패턴, 시사점
    """
    try:
        agent = _get_taxtr_agent()
        result = agent.ask(question)
        return result
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# 서버 실행
# ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
