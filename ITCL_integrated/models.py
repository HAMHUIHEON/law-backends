#ITCL_integrated/models.py

from pydantic import BaseModel
from typing import List, Optional, Dict, Literal, Any
from pydantic import BaseModel, Field, field_validator

#semantic
class IntegratedIssueSemantic(BaseModel):
    issue_id: str
    issue_title: str
    issue_summary: str
    conditions: List[str]
    effects: List[str]
    exceptions: List[str] = []
    methods: List[str]
    cross_refs: List[Dict[str, Any]]


class IntegratedChapterSemanticInput(BaseModel):
    chapter_id: str
    chapter_name: str
    domain: str
    text: str   # 법 + 시행령 + 시행규칙 통합 텍스트


class IntegratedChapterSemanticOutput(BaseModel):
    chapter_id: str
    chapter_name: str
    domain: str
    chapter_summary: str
    issues: List[IntegratedIssueSemantic]

#reasoning
class IntegratedChapterReasoningInput(BaseModel):
    chapter_id: str
    chapter_name: str
    text: str  # chapter 전체 텍스트


class IntegratedReasoningStep(BaseModel):
    step_id: str                           # "1", "2", "3" …
    step_type: str                         # "condition_check", "apply_rule", "exception_check", "priority_order", "method_apply"
    description: str                       # 이 단계에서 무엇을 판단/적용하는지 자연어 설명
    based_on: List[str]                    # ["제22조", "제23조", ...] 사람에게 친숙한 citation
    conditions: List[str] = []             # 이 단계에서 판단하는 조건
    effects: List[str] = []                # 이 단계에서 발생하는 효과
    exceptions: List[str] = []             # 단계적 override 구조
    methods: List[str] = []                # 산식 / 계산 / 절차가 들어가는 경우만


class IntegratedIssueReasoning(BaseModel):
    issue_title: str
    summary: str                            # 시멘틱의 issue_summary를 축약 or 재구성
    steps: List[IntegratedReasoningStep]              # 논리적 흐름(Flow)


class IntegratedChapterReasoningOutput(BaseModel):
    chapter_id: str
    chapter_name: str
    reasoning: List[IntegratedIssueReasoning]



#시멘틱-리즈닝 연결

class SemanticIssueLite(BaseModel):
    issue_id: str
    issue_title: str
    issue_summary: str

class ReasoningIssueLite(BaseModel):
    reasoning_issue_index: int   # ✅ int
    issue_title: str
    summary: str

class ChapterAlignmentInput(BaseModel):
    chapter_id: str
    semantic_issues: List[SemanticIssueLite]
    reasoning_issues: List[ReasoningIssueLite]


class AlignmentItem(BaseModel):
    reasoning_issue_index: int              # reasoning 배열 인덱스 # 1-based index
    semantic_issue_id: Optional[str]        # "ISSUE_4" or null
    confidence: Literal["HIGH", "MED", "LOW"]
    rationale: str                          # 1~2문장, 짧게 (디버깅용)

class ChapterAlignmentOutput(BaseModel):
    chapter_id: str
    alignments: List[AlignmentItem]



