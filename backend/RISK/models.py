

#revision Observation Chain
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from datetime import date


ChangeType = Literal[
    "PROCEDURALIZE",
    "REDEFINE",
    "SCOPE_LIMIT",
    "NEUTRAL"
]

TargetKind = Literal[
    "CONCEPT",
    "DEFINITION",
    "REQUIREMENT",
    "PROCEDURE"
]

SourceType = Literal[
    "REVISION_REASON",
    "REVISION_TEXT"
]

class RevisionObservationInput(BaseModel):
    law_name: str
    law_type: Literal["LAW", "DECREE", "RULE"]
    promulgated_at: str              # "YYYYMMDD"
    effective_at: Optional[str] = None  # "YYYYMMDD" or None
    revision_reason: str
    revision_text: str

class ChangeBasis(BaseModel):
    source_type: SourceType
    excerpt: str

class ChangeTarget(BaseModel):
    kind: TargetKind
    label: str


class ObservedChange(BaseModel):
    change_type: ChangeType
    target: ChangeTarget
    description: str
    basis: List[ChangeBasis]


class RevisionObservationOutput(BaseModel):
    law_name: str # 법 이름
    law_type: Literal["LAW", "DECREE", "RULE"]
    promulgated_at: str #공포일자
    effective_at: str #시행일자
    observed_changes: List[ObservedChange] = Field(default_factory=list)
    notes: Optional[str] = None

#부칙
class AddendaObservationInput(BaseModel):
    law_name: str
    law_type: Literal["LAW", "DECREE", "RULE"]

    addenda_date: str
    addenda_text: str

AddendumRole = Literal[
    "ACTIVATION",            # 시행 선언
    "DEFERRED_ACTIVATION",   # 부분 시행 유예
    "APPLICABILITY",         # 적용례
    "TRANSITION",            # 경과조치
    "FORM_CONTINUITY",       # 서식 경과 특칙
    "CONTINUITY_CLAUSE",     # 종전 부칙 효력 유지
    "EXTERNAL_IMPACT"        # 타법/타규범 영향
]

class AddendumRoleItem(BaseModel):
    role: AddendumRole

    description: str
    # 사람이 읽었을 때 "이 조항이 무슨 역할을 하는지" 한 문장 설명
    # 평가/중요도/리스크 금지

    excerpt: str
    # 부칙 원문 중 해당 role을 뒷받침하는 핵심 발췌

class AddendaObservationOutput(BaseModel):
    law_name: str
    law_type: Literal["LAW", "DECREE", "RULE"]

    addenda_date: str  # YYYYMMDD 그대로, merge anchor

    summary: Optional[str] = None
    # 부칙 전체의 성격 요약 (있으면 좋고, 없으면 None)

    roles: List[AddendumRoleItem] = Field(default_factory=list)
    # 부칙 안에서 관측된 역할들의 목록

#별표
AnnexRole = Literal[
    "CALCULATION_INTERFACE",
    "REPORTING_INTERFACE",
    "REQUEST_INTERFACE",
    "ADMIN_NOTICE",
    "STATUS_DISCLOSURE",
    "SANCTION_TABLE",
    "DESIGNATION_AGREEMENT",
]

class AnnexObservationInput(BaseModel):
    annex_id: str
    title: str
    content: str


class RelatedArticle(BaseModel):
    article_ref: str        # 예: "법 제63조", "시행령 제125조의2"
    excerpt: str            # 해당 조문이 언급된 원문 일부

class AnnexObservationOutput(BaseModel):
    annex_id: str
    title: str

    role: AnnexRole

    description: str
    # 이 별표가 실무상 어떤 기능을 수행하게 만드는지 2~4문장

    related_articles: List[RelatedArticle] = Field(default_factory=list)





## 후속 조치 필요함
class IntegratedRevisionFeatureInput(BaseModel):
    chapter_id: str
    chapter_name: str
    text: str  # 법+시행령+시행규칙 통합 본문(Chapter 단위)

    law_revision_text: str = ""     # (없으면 빈 문자열)
    decree_revision_text: str = ""
    rule_revision_text: str = ""

class ChangeScope(BaseModel):
    law: Literal["핵심 규범 변경", "경미", "없음"]
    decree: Literal["절차 구체화 강화", "경미", "없음"]
    rule: Literal["신고·서식 중심 변경", "경미", "없음"]

class RiskSignal(BaseModel):
    type: Literal["LEGAL_STABILITY", "OPS_BURDEN", "STRUCTURAL_COMPLEXITY", "EXTERNAL_DEPENDENCY"]
    level: Literal["HIGH", "MED", "LOW"]
    reason: str  = Field(default_factory=str, description ="왜 이 리스크가 발생하는지 조문 및 개정 맥락을 근거로 설명(1~3문장)")
    citations: List[str]= Field(default_factory=list, description="근거 조문/부칙/별표 목록 (예: 국제조세조정에 관한 법률 제2조 제2항, 국제조세조정에 관한 법률 시행령 제70조의2, 부칙 제1조")

class IntegratedRevisionFeatureOutput(BaseModel):
    chapter_id : str
    summary: str = Field(description="5~7문장. 최근 개정·재개정의 성격과 왜 리스크로 이어지는지 요약")
    change_triggers: List[str] = Field(default_factory=list, description="개정의 동인/배경(입력 근거 기반)")
    change_scope: ChangeScope
    risk_signals: List[RiskSignal] = Field(description="2~4개 권장. type 중복 가능하지만 reason은 달라야 함.")
    affected_areas: List[str] = Field(default_factory=list, description="업무·규범 영향 영역(예: 신고, 문서화, 제출 등)")

