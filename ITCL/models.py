#ITCL/models.py

ARTICLE_ANALYSIS_TEMPLATE = {
    "law_id": None,
    "article_id": None,
    "article_no": None,
    "title": None,
    "domain": None,
    "summary": None,
    "purpose": None,
    "key_topics": [],
    "norm_units": [],
    "reasoning_units": [],
    "notes": {
        "complexity": None,
        "risk_level": None,
        "is_key_article": None,
    },
}
ARTICLE_ANALYSIS_SCHEMA ="""
{
  "law_id": "000603",
  "article_id": "ART_8",          // 그래프 상 Article 노드 id
  "article_no": "8",
  "title": "정상가격의 산출방법",
  "domain": "TP_CORE",            // 기본은 구조에서 상속, 필요시 override

  "summary": "",                  // 이 조의 한 줄 요약 (자연어)
  "purpose": "",                  // 입법 취지 / 기능 요약

  "key_topics": [                 // LLM이 뽑는 토픽 태그 (자연어, 3~7개)
    "정상가격 산출방법",
    "비교가능 제3자 가격방법",
    "거래순이익률방법"
  ],

  "norm_units": [],               // 아래 NORM_UNIT 스키마의 리스트
  "reasoning_units": [],          // 선택: 필요하면 정의해 두고 초기엔 비워도 됨

  "notes": {                      // LLM이 느낀 메타 정보 (optional)
    "complexity": "HIGH",         // LOW / MEDIUM / HIGH
    "risk_level": "MEDIUM",       // TAX RISK 기준
    "is_key_article": true        // 법 전체 구조에서 중요도 플래그
  }
}
"""


NORM_UNIT_TEMPLATE = {
    "id_suffix": None,
    "level": None,
    "ref": {
        "para_no": None,
        "item_no": None,
        "subitem_no": None,
    },
    "roles": [],
    "short_label": None,
    "summary": None,
    "conditions": [],
    "effects": [],
    "exceptions": [],
    "methods": [],
    "cross_refs": [],
}


Norm_Unit ="""
{
  "id_suffix": "1",              // 최종 id는 f"{article_id}-{id_suffix}"
  "level": "ARTICLE",            // ARTICLE / PARAGRAPH / ITEM / SUBITEM

  "ref": {                       // 이 규범이 붙는 위치 (그래프 매핑용)
    "para_no": null,             // "1" | "2" | null
    "item_no": null,             // "1" | "2" | null
    "subitem_no": null           // "1" | "가" | null
  },

  "roles": [                     // 이 규범의 기능 (복수 가능)
    "DEFINITION",                // 용어 정의
    "METHOD_CORE",               // 계산/산출방법의 핵심 규칙
    "CONDITION",                 // 적용 요건/전제
    "SCOPE",                     // 적용 범위
    "EXCEPTION",                 // 예외
    "PROCEDURE",                 // 절차
    "PENALTY",                   // 벌칙/제재
    "COMPLIANCE",                // 신고·자료제출·기한 등
    "RELIEF",                    // 구제·조정·완화 등
    "REFERENCE_ONLY"             // 규범이라기보단 단순 인용
  ],

  "short_label": "",             // 한 줄 이름 (예: "정상가격 산출 기본 5방법")
  "summary": "",                 // 사람이 읽기 좋은 설명 (2~4문장)

  "conditions": [                // “언제 적용되냐”
    "거주자가 국외특수관계인과 국제거래를 하는 경우",
    "비교가능 거래가 존재하는 경우"
  ],
  "effects": [                   // “적용되면 어떤 결과가 나오냐”
    "정상가격은 비교가능 제3자 가격에 따라 산출한다.",
    "정상가격 산출 결과는 과세표준 계산에 사용한다."
  ],
  "exceptions": [                // 예외 / 특례
    "비교가능 거래가 없는 경우에는 다른 정상가격 산출방법을 사용한다."
  ],

  "methods": [                   // TP 관련이면 여기에 코드로
    "CUP", "RP", "CP", "TNMM", "PS"
  ],

  "cross_refs": [                // 관련 규정/법령/조문
    {
      "type": "INTERNAL",        // INTERNAL / EXTERNAL
      "target_law_id": "000603",
      "target_article_no": "6",
      "note": "정상가격에 의한 신고 및 경정청구와 연결"
    }
  ]
}
"""

REASONING_UNIT_TEMPLATE = {
    "id_suffix": None,
    "ref": {
        "para_no": None,
        "item_no": None,
        "subitem_no": None,
    },
    "logic_type": None,
    "premises": [],
    "conclusion": None,
    "linked_norm_units": [],
}
Resaoning_unit= """
{
  "id_suffix": "R1",
  "ref": {
    "para_no": "1",
    "item_no": null,
    "subitem_no": null
  },
  "logic_type": "IF_THEN",            // IF_THEN / BALANCING / ENUMERATION / DEEMING_FICTION ...
  "premises": [
    "거주자가 국외특수관계인과 거래를 한다.",
    "그 거래가 통상의 거래와 차이가 있다."
  ],
  "conclusion": "세무당국은 정상가격을 기준으로 과세표준을 조정할 수 있다.",
  "linked_norm_units": ["ITCL_8-1"]   // 위에서 만든 norm_unit id들과 연결
}
"""

llm_input = """
{
  "law_meta": {
    "law_id": "000603",
    "law_name": "국제조세조정에 관한 법률"
  },
  "structure_context": {
    "chapter": { "id": "CH_2", "name": "제2장 국제거래에 관한 조세의 조정", "domain": "TP" },
    "section": { "id": "CH_2_SEC_1", "name": "제1절 국외특수관계인과의 거래에 대한 과세조정", "domain": "TP_CORE" },
    "subdivision": { "id": "CH_2_SEC_1_SUB_1", "name": "제1관 정상가격 등에 의한 과세조정", "domain": "TP_CORE" }
  },
  "article": {
    "article_id": "ART_8",
    "article_no": "8",
    "title": "제8조(정상가격의 산출방법)",
    "reference_notes": ["[본조신설 2022.12.31]"],
    "raw_text": "제8조(정상가격의 산출방법) ① ... ② ... ③ ...",   // 항/호/목 포함 줄글 버전
    "paragraphs": [ /* 필요하면 구조도 같이 */ ]
  }
}
"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Literal, Any
from pydantic import BaseModel, Field, field_validator

#article_summary
class ArticleSummaryInput(BaseModel):
  article_id: str
  law_name:str #law_meta의 law_name, ex: 국제조세조정에 관한 법률
  title:str #article 조문 제목 ex:제8조(정상가격의 산출방법)
  raw_text: str
  domain:str
    
class ArticleSummaryOutput(BaseModel):
  article_id: str
  article_summary: str
  article_purpose: str
  article_key_topics: List[str]

#morm_unit1차
class NormUnitInput(BaseModel):
    article_id: str
    text: str
    ref: dict
    level: str
    domain: str

class NormUnitOutput(BaseModel):
    article_id: str
    level: str
    ref: dict
    roles: List[str]
    short_label: str

"""
UNWIND $cross_refs as ref
MATCH (s:NormUnit {id: $source_id})
MATCH (t:NormUnit {target_string: ref.target})
CREATE (s)-[:REFERS_TO {type: ref.type, note: ref.note}]->(t);
"""
#norm_unit2차 cross-refs
class NormUnitCrossRefInput(BaseModel):
    article_id: str
    text: str           # 해당 규범 단위 원문
    ref: dict           # para_no / item_no / subitem_no
    level: str          # ARTICLE / PARAGRAPH / ITEM / SUBITEM

class NormUnitCrossRef(BaseModel):
    type: Literal["INTERNAL", "EXTERNAL"]
    target: str                   # "국기법 제2조 제1항"
    note: Optional[str] = None

class NormUnitCrossRefOutput(BaseModel):
    article_id: str
    level: str
    ref: dict                    # para_no, item_no, subitem_no
    cross_refs: List[NormUnitCrossRef]


#pass0 Chapter Semantic
from typing import List, Dict, Any
from pydantic import BaseModel

class IssueSemantic(BaseModel):
    issue_id: str
    issue_title: str
    issue_summary: str
    conditions: List[str]
    effects: List[str]
    exceptions: List[str] = []   # 빠져있었음
    methods: List[str]
    cross_refs: List[Dict[str, Any]]  # 최소한 dict 리스트로는 정의해야 함


class ChapterSemanticInput(BaseModel):
    chapter_id: str
    chapter_name: str
    domain: str
    text: str   # chapter 전체 텍스트


class ChapterSemanticOutput(BaseModel):
    chapter_id: str
    chapter_name: str
    domain: str
    chapter_summary: str
    issues: List[IssueSemantic]

#reasoning_unit

class ChapterReasoningInput(BaseModel):
    chapter_id: str
    chapter_name: str
    text: str  # chapter 전체 텍스트


class ReasoningStep(BaseModel):
    step_id: str                           # "1", "2", "3" …
    step_type: str                         # "condition_check", "apply_rule", "exception_check", "priority_order", "method_apply"
    description: str                       # 이 단계에서 무엇을 판단/적용하는지 자연어 설명
    based_on: List[str]                    # ["제22조", "제23조", ...] 사람에게 친숙한 citation
    conditions: List[str] = []             # 이 단계에서 판단하는 조건
    effects: List[str] = []                # 이 단계에서 발생하는 효과
    exceptions: List[str] = []             # 단계적 override 구조
    methods: List[str] = []                # 산식 / 계산 / 절차가 들어가는 경우만


class IssueReasoning(BaseModel):
    issue_title: str
    summary: str                            # 시멘틱의 issue_summary를 축약 or 재구성
    steps: List[ReasoningStep]              # 논리적 흐름(Flow)


class ChapterReasoningOutput(BaseModel):
    chapter_id: str
    chapter_name: str
    reasoning: List[IssueReasoning]



 