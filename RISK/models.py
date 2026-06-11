

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





# ────────────────────────────────────────────────────────────────────────────
# 컨설팅 인사이트
# ────────────────────────────────────────────────────────────────────────────

ConsultingCategory = Literal[
    "절세",           # 개정으로 새로 생긴 감면·공제·유예 활용
    "경정청구",        # 소급 적용 또는 해석 변화 → 기납부세액 환급 가능
    "의무_이행",       # 새 신고·서식·제출·기한 의무 — 놓치면 가산세
    "사전_검토",       # 조직·거래 구조 재검토가 필요한 경우
]

UrgencyLevel = Literal["즉시", "단기", "중기"]  # 즉시=이미 시행, 단기=3개월내, 중기=6개월내


class ConsultingItem(BaseModel):
    category: ConsultingCategory
    title: str = Field(description="컨설팅 주제를 한 줄로 — 예: '이전가격 문서화 의무 신설로 미이행 시 가산세 위험'")
    description: str = Field(description="구체적 내용 2~4문장. 어떤 조문이 바뀌어 어떤 영향이 생기는지.")
    target_clients: List[str] = Field(description="이 항목이 해당되는 고객군 — 예: ['다국적기업', '외국인투자법인']")
    action: str = Field(description="세무사로서의 권고 행동 1~2문장 — 예: '경정청구서 작성·제출' 또는 '내부 정책 검토 회의 일정 잡기'")
    urgency: UrgencyLevel
    legal_basis: List[str] = Field(description="관련 조문·부칙·별표 — 예: ['법 제13조', '부칙 제3조(적용례)']")


class ConsultingInsightOutput(BaseModel):
    law_name: str
    law_type: Literal["LAW", "DECREE", "RULE"]
    promulgated_at: str
    effective_at: str
    overall_priority: Literal["HIGH", "MED", "LOW"] = Field(
        description="이 개정이 실무 대응을 얼마나 급하게 요구하는지 종합 판단"
    )
    executive_summary: str = Field(
        description="3~5문장. 어떤 개정이 왜 컨설팅 기회 또는 위험이 되는지 — 클라이언트에게 전달할 수 있는 수준."
    )
    items: List[ConsultingItem] = Field(
        default_factory=list,
        description="컨설팅 항목 2~6개. 실무 영향이 없는 중립적 개정이면 빈 리스트도 허용."
    )


# ────────────────────────────────────────────────────────────────────────────
# 외부 법령 → 세법 연동 영향 분석
# ────────────────────────────────────────────────────────────────────────────

CrossImpactType = Literal[
    "DEDUCTION_CHANGE",    # 감면·공제 신설·변경·일몰
    "EXEMPTION_CHANGE",    # 비과세·면제 범위 변동
    "PROCEDURE_CHANGE",    # 신고·제출·기한 연동 변경
    "SCOPE_CHANGE",        # 과세 대상·범위 연동 변경
    "DEFINITION_CHANGE",   # 용어·개념 변경으로 세법 해석 영향
    "PENALTY_CHANGE",      # 가산세·제재 연동 변경
]


class CrossImpactItem(BaseModel):
    impact_type: CrossImpactType
    source_law: str = Field(description="변경된 외부 법령명")
    source_provision: str = Field(description="외부 법령 중 변경된 조문/조항 참조 — 예: 조세특례제한법 제5조제1항")
    affected_tax_law: str = Field(description="영향받는 세법명 — 예: 법인세법")
    affected_provision: str = Field(description="영향받는 세법 조문 참조 — 예: 법인세법 제24조(기부금 손금산입)")
    description: str = Field(description="어떤 영향이 발생하는지 2~4문장으로 설명")
    consulting_point: str = Field(description="납세자 또는 세무사 관점의 대응 포인트 1~2문장")
    urgency: Literal["즉시", "단기", "중기"]


class CrossLawImpactOutput(BaseModel):
    source_law: str
    source_version_key: str
    items: List[CrossImpactItem] = Field(
        default_factory=list,
        description="연동 영향 항목. 세법 영향이 없으면 빈 리스트."
    )
    summary: str = Field(
        description="2~4문장. 이 외부 법령 개정이 세법 전반에 미치는 영향 요약."
    )


# ────────────────────────────────────────────────────────────────────────────
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

