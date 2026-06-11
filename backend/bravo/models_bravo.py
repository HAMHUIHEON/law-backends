#bravo/models.py

from pydantic import BaseModel
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, field_validator


#pass_base_a
class BravoTopicInput(BaseModel):
    full_text: str
    
class BravoNarrativeOutput(BaseModel):
    fact_summary: str = ""
    plaintiff_arguments: List[str] = Field(default_factory=list)
    defendant_arguments: List[str] = Field(default_factory=list)
    legal_context: List[str] = Field(default_factory=list)
    court_reasoning: List[str] = Field(default_factory=list)
    core_conflicts: List[str] = Field(default_factory=list)

#pass_base_b
class BravoKeywordInput(BaseModel):
    core_conflict: str   # 단일 쟁점

class BravoKeywordOutput(BaseModel):
    keywords: List[str]
    
#pass_base_b-1
class BravoSignatureInput(BaseModel):
    keywords: List[str]

class BravoSignatureOutput(BaseModel):
    clusters: Dict[str, List[str]]

#pass0
class BravoIssueInput(BaseModel):
    full_text: str         # narrative_chunk → full_text 교체
    keywords: List[str]    # signature의 대표 키워드만

class IssueGroup(BaseModel):
    plaintiff_arguments: List[str] = Field(default_factory=list)
    defendant_arguments: List[str] = Field(default_factory=list)
    legal_context: List[str] = Field(default_factory=list)
    court_reasoning: List[str] = Field(default_factory=list)

class BravoIssueOutput(BaseModel):
    issue_groups: Dict[str, IssueGroup] = Field(default_factory=dict)


#Pass1
class BravoGlobalInput(BaseModel):
    full_text: str

class IssueLogic(BaseModel):
    issue: str
    premise: Optional[str] = None
    evidence: Optional[str] = None
    rule: Optional[str] = None
    application: Optional[str] = None
    inference: Optional[str] = None
    mini_conclusion: Optional[str] = None
    citations: List[dict] = Field(default_factory=list)
    uid: Optional[str] = None  # ✅ 추가 (UI/프론트 key용)
    
class BravoGlobalOutline(BaseModel):
    global_outline: str
    main_issues: List[str] = Field(default_factory=list)
    issue_logic_chains: List[IssueLogic] = Field(default_factory=list)


from enum import Enum
#Pass2- Citation
class BravoIssueCitationInput(BaseModel):
    issue: str
    full_text: str  # premise ~ mini_conclusion 이어붙인 단일 청크

class CitationSource(str, Enum):
    statute = "statute"
    case = "case"

class CitationItem(BaseModel):
    source_type: CitationSource
    title: str
    citation_text: Optional[str] = None
    promulgation_no: Optional[str] = None   # 예: "19893" (대통령령 제19893호)
    promulgation_type: Optional[str] = None # "법률" | "대통령령" | "부령" | "조약"
    is_prior_version: bool = False          # "개정되기 전의 것" 여부
    effective_before: Optional[str] = None  # 해당 버전이 유효한 기준일 (예: "2007-02-28")
    matched_version: Optional[dict] = None  # Neo4j 또는 Claude 조회 결과

class BravoIssueCitationOutput(BaseModel):
    issue: str = ""
    citations: List[CitationItem] = Field(default_factory=list)
