#export/models_export.py

from pydantic import BaseModel, Field, field_validator
from typing import List
#export A

class ExportAInput(BaseModel):
    narrative_json:dict
    
class ExportAExecSummary(BaseModel):
    what_this_case_is_about: str
    key_points_in_20_words: List[str]
    micro_takeaway: str

class ExportAOutput(BaseModel):
    executive_summary: ExportAExecSummary


#export B
class ExportBInput(BaseModel):
    narrative_json:dict
    issue_frame:dict
    
class ExportBExecSummary(BaseModel):
    one_liner: str
    main_conflicts: List[str]
    legal_direction: str
    practical_implication:str

class ExportBOutput(BaseModel):
    executive_summary: ExportBExecSummary

#export C
from bravo.models_bravo import IssueLogic

class ExportCInput(BaseModel):
    issue_logic_list: List[IssueLogic]   # citations 포함된 논증 구조
    block_texts: List[str]               # 블록 단위 원문 텍스트 (str 리스트)

class JudicialLogic(BaseModel):
    how_the_court_thought: str = Field(..., description="법원의 핵심 논증 결론 한 단락")            
    legal_context: List[str] = Field(
        default_factory=list,
        description="판결문에 기반해 법원이 강조한 핵심 법리·논리 포인트 3~5개"
)

class PartyPositions(BaseModel):
    taxpayer: str = Field(..., description="납세자 포지션 요약")                        
    tax_authority: str = Field(..., description="과세관청 포지션 요약")                    
    contrasting_points: List[str]  = Field(default_factory=list, description="당사자의 충돌 쟁점 포인트")           

class RiskView(BaseModel):
    taxpayer_risk: str = Field(..., description="납세자 입장에서 주의할 포인트")                              
    tax_authority_risk: str= Field(..., description="과세당국 집행 리스크/한계")                         
    precedent_signal: str = Field(..., description="이 판례가 향후 유사 사건에 주는 시그널·법리 방향성·실무 기준")                     

class ExportCExecSummary(BaseModel):
    one_liner: str                           # 1줄 요약 (최대 40~50자 느낌)
    core_issues: List[str]                   # 2~4개 쟁점/핵심 포인트
    judicial_logic: JudicialLogic
    party_positions: PartyPositions
    risk_view: RiskView

class ExportCOutput(BaseModel):
    executive_summary: ExportCExecSummary
