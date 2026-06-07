# agents/self_reflection.py
#
# Export C 결과물을 스스로 비평하고 개선하는 Self-Reflection Agent.
# LangGraph: critique → [pass?] → refine → critique → ... (최대 max_iterations 반복)

import json
import re
from typing import TypedDict, Optional, Literal

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from export.models_export import ExportCOutput, ExportCInput
from export.prompt import EXPORT_C_PROMPT


# ── Prompts ───────────────────────────────────────────────────────────────────

CRITIQUE_PROMPT = """
당신은 조세법률 판례 분석 보고서의 품질 검토 전문가다.
아래 Executive Summary(Export C)를 검토하고 약점을 찾아라.

[평가 기준]
1. one_liner: 판결 본질을 정확히 압축했는가? 너무 추상적이지 않은가?
2. core_issues: 판결이 실제로 해결하려 한 핵심 쟁점을 빠짐없이 담았는가?
3. judicial_logic.how_the_court_thought: 법원의 논증 구조를 충분히 설명하는가?
4. judicial_logic.legal_context: 포인트가 실무적으로 의미 있는가?
5. party_positions: 납세자/과세관청 포지션의 구조적 약점이 드러나는가?
6. risk_view.taxpayer_risk / tax_authority_risk: "어떤 상황에서" 리스크가 현실화되는지 설명하는가?
7. risk_view.precedent_signal: 실무자가 행동할 수 있는 구체적 인사이트를 주는가?

[출력 형식 — 반드시 아래 JSON만 출력]
{{
  "passed": true or false,
  "score": 1~5,
  "weaknesses": ["약점1", "약점2"],
  "improvement_guide": "개선 방향 (2~4문장)"
}}

판정 기준:
- passed=true : score 4 이상이고 치명적 약점 없음
- passed=false: score 3 이하이거나 치명적 약점 존재

[검토 대상]
{executive_summary_json}
"""

REFINE_PROMPT = """
당신은 조세법률 사건을 분석하는 하이엔드 리서치 센터의 시니어 분석관이다.
아래 Executive Summary 초안의 약점을 보완하여 더 정확하고 실무적인 분석을 생성하라.

[개선 방향]
{improvement_guide}

[구체적 약점]
{weaknesses}

[원본 판례 데이터 — 이 범위에서만 근거를 찾을 것]
ISSUE_LOGIC_LIST:
{issue_logic_list}

BLOCK_TEXTS:
{block_texts}

[기존 초안 — 잘된 부분은 유지하고, 약점으로 지적된 부분만 집중 개선]
{current_output_json}

[출력 규칙]
- 제공된 데이터 범위 내에서만 추론 (새 사실·법령·판례 생성 금지)
- 기존 구조(JSON 스키마)를 그대로 유지

{format_instructions}
"""


# ── Pydantic models ───────────────────────────────────────────────────────────

class CritiqueResult(BaseModel):
    passed: bool
    score: int = Field(..., ge=1, le=5)
    weaknesses: list[str] = Field(default_factory=list)
    improvement_guide: str = Field(default="")


# ── State ─────────────────────────────────────────────────────────────────────

class ReflectionState(TypedDict):
    # 직렬화된 원본 입력 (refine 시 근거로 사용)
    issue_logic_list_str: str
    block_texts_str: str
    # 현재 분석 결과 (dict)
    current_output: dict
    # 비평 결과
    critique: Optional[dict]
    # 반복 제어
    iteration: int
    max_iterations: int
    passed: bool


# ── Nodes ─────────────────────────────────────────────────────────────────────

def critique_node(state: ReflectionState) -> ReflectionState:
    llm = ChatOpenAI(model="gpt-4.1", temperature=0)

    prompt = CRITIQUE_PROMPT.format(
        executive_summary_json=json.dumps(
            state["current_output"], ensure_ascii=False, indent=2
        )
    )

    raw = llm.invoke(prompt).content
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
        critique = CritiqueResult(**data)
    except Exception:
        critique = CritiqueResult(passed=True, score=4, weaknesses=[], improvement_guide="")

    return {
        **state,
        "critique": critique.model_dump(),
        "passed": critique.passed,
    }


def refine_node(state: ReflectionState) -> ReflectionState:
    llm = ChatOpenAI(model="gpt-4.1", temperature=0)
    parser = PydanticOutputParser(pydantic_object=ExportCOutput)

    critique = state["critique"]
    weaknesses_text = "\n".join(f"- {w}" for w in critique.get("weaknesses", []))

    prompt = PromptTemplate(
        template=REFINE_PROMPT,
        input_variables=[
            "improvement_guide", "weaknesses",
            "issue_logic_list", "block_texts", "current_output_json",
        ],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    msg = (prompt | llm).invoke({
        "improvement_guide": critique.get("improvement_guide", ""),
        "weaknesses": weaknesses_text,
        "issue_logic_list": state["issue_logic_list_str"],
        "block_texts": state["block_texts_str"],
        "current_output_json": json.dumps(state["current_output"], ensure_ascii=False, indent=2),
    })

    try:
        refined: ExportCOutput = parser.parse(msg.content)
        new_output = refined.model_dump()
    except Exception:
        new_output = state["current_output"]

    return {
        **state,
        "current_output": new_output,
        "iteration": state["iteration"] + 1,
    }


# ── Conditional edge ──────────────────────────────────────────────────────────

def should_continue(state: ReflectionState) -> Literal["refine", "__end__"]:
    if state["passed"] or state["iteration"] >= state["max_iterations"]:
        return "__end__"
    return "refine"


# ── Graph builder ─────────────────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(ReflectionState)
    g.add_node("critique", critique_node)
    g.add_node("refine", refine_node)
    g.set_entry_point("critique")
    g.add_conditional_edges("critique", should_continue)
    g.add_edge("refine", "critique")
    return g.compile()


# ── Public API ────────────────────────────────────────────────────────────────

class SelfReflectionAgent:
    """
    Export C 결과물을 비평·개선하는 Self-Reflection Agent.

    Usage:
        agent = SelfReflectionAgent(max_iterations=2)
        result = agent.run(export_c_input, initial_export_c_output)

        result["output"]         # 최종 개선된 ExportCOutput (dict)
        result["iterations"]     # 실제 수행된 refine 횟수
        result["passed"]         # 마지막 critique 통과 여부
        result["final_critique"] # 마지막 비평 내용
    """

    def __init__(self, max_iterations: int = 2):
        self.max_iterations = max_iterations
        self.graph = _build_graph()

    def run(self, export_c_input: ExportCInput, initial_output: ExportCOutput) -> dict:
        state: ReflectionState = {
            "issue_logic_list_str": json.dumps(
                [item.model_dump() for item in export_c_input.issue_logic_list],
                ensure_ascii=False, indent=2,
            ),
            "block_texts_str": json.dumps(
                export_c_input.block_texts,
                ensure_ascii=False, indent=2,
            ),
            "current_output": initial_output.model_dump(),
            "critique": None,
            "iteration": 0,
            "max_iterations": self.max_iterations,
            "passed": False,
        }

        final = self.graph.invoke(state)
        return {
            "output": final["current_output"],
            "iterations": final["iteration"],
            "passed": final["passed"],
            "final_critique": final["critique"],
        }
