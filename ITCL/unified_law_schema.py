# ITCL / unified_law_schema.py

"""
통합 법령 스키마 
(LAW → Chapter → Section → Subdivision → Article → Paragraph → Item → Subitem)

LAW
 └── chapters[]
       └── sections[]
            └── subdivisions[]
                 └── articles[]
                      ├── article metadata (시행일자/변경여부/참고자료)
                      └── paragraphs[]
                           └── items[]
                                └── subitems[]

"""

"""
통합 시행규칙 스키마 

법령
 ├── 기본정보
 ├── 조문
 ├── 제개정이유
 ├── 개정문
 └── 부칙

administrative_law
 └── chapters[]
       └── sections[]
            └── subdivisions[]
                 └── articles[]
                      ├── paragraphs[]
                           └── items[]
                                └── subitems[]
    ├── amendments[]
    └── revision_reasons[]

"""
# 통합 스키마 (Schema)

#1) LAW 객체
LAW_SCHEMA = {
    "law_id": None,
    "law_name": None,    # ex: "국제조세조정에 관한 법률"
    "source_type": None,
    "metadata": {
        "시행일자": None,
        "공포일자": None,
        "공포번호": None,
        "법종구분": None,
        "소관부처": None
    },

    "chapters": [],      # 장/절/관/조문 구조 (법과 동일)
    "addenda": [],       # 부칙

    "amendments": [],        # 개정문 내용
    "revision_reasons": [],  # 제개정 이유
    "annexes": []            # 별표
}

# -----------------------
# 템플릿 (법률과 유사하지만 prefix 추가)
# -----------------------

#2) 장 객체
CHAPTER_TEMPLATE = {
    "id": None,
    "type": "CHAPTER",
    "name": None,
    "domain": None,
    "sections": []
}

#3) 절 객체
SECTION_TEMPLATE = {
    "id": None,
    "type": "SECTION",
    "name": None,
    "domain": None,
    "subdivisions": []
}

#4) 관 객체
SUBDIVISION_TEMPLATE = {
    "id": None,
    "type": "SUBDIVISION",
    "name": None,
    "domain": None,
    "articles": []
}

#5) 조 객체
ARTICLE_TEMPLATE = {
    "id": None,
    "type": "ARTICLE",

    "article_no": None,
    "title": None,

    "effective_date": None,
    "changed": False,
    "reference_notes": [],

    "raw_text": None,
    "domain": None,

    "paragraphs": [],

    "norm_units": [],
}

#6) 항 객체
PARAGRAPH_TEMPLATE = {
    "para_no": None,
    "text": None,
    "changed": False,
    "effective_date": None,
    "items": []
}

#7) 호 객체
ITEM_TEMPLATE = {
    "item_no": None,
    "text": None,
    "subitems": []
}

#8) 목 객체
SUBITEM_TEMPLATE = {
    "subitem_no": None,
    "text": None
}

# 별표(ANNEX) 템플릿
ANNEX_TEMPLATE = {
    "id": None,
    "title": None,
    "number": None,
    "content_raw": None,
    "images": [],
    "pdf": None,
    "hwp": None
}

# 개정문/제개정 이유 템플릿
AMENDMENT_TEMPLATE = {
    "text": None,
}

REV_REASON_TEMPLATE = {
    "text": None,
}

# 별표(ANNEX) 템플릿
ANNEX_TEMPLATE = {
    "id": None,
    "title": None,
    "number": None,
    "content_raw": None,
    "images": [],
    "pdf": None,
    "hwp": None
}


