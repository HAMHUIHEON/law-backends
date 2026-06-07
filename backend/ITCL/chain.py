from typing import List, Optional, Dict
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate,PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from ITCL.prompts import (ARTICLE_SUMMARY, NORM_UNIT_PROMPT,CROSS_REF,CHAPTER_SEMANTICS,
                          REASONING)
from ITCL.models import (ArticleSummaryInput,ArticleSummaryOutput,
                         NormUnitInput,NormUnitOutput,NormUnitCrossRefInput,
                         NormUnitCrossRefOutput,ChapterSemanticInput,ChapterSemanticOutput,
                         ChapterReasoningOutput,ChapterReasoningInput)

class ArticleSummaryChain:
    def __init__(self, model: str = "gpt-5.1"):
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=ArticleSummaryOutput)

        self.prompt = PromptTemplate(
            template=ARTICLE_SUMMARY,
            input_variables=["article_id","law_name","title","raw_text","domain"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def summary(self, inp:ArticleSummaryInput) -> ArticleSummaryOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "article_id":inp.article_id,
            "law_name": inp.law_name,
            "title": inp.title,
            "raw_text":inp.raw_text,
            "domain":inp.domain
        })
#norm_unit1차
class NormUnitChain:
    def __init__(self, model: str = "gpt-5.1"):
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=NormUnitOutput)

        self.prompt = PromptTemplate(
            template=NORM_UNIT_PROMPT,
            input_variables=[
                "article_id",
                "text",
                "level",
                "domain",
                "para_no",
                "item_no",
                "subitem_no",
            ],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def tag(self, inp: NormUnitInput) -> NormUnitOutput:
        ref = inp.ref or {}
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "article_id": inp.article_id,
            "text": inp.text,
            "level": inp.level or "",
            "domain": inp.domain or "",
            "para_no": ref.get("para_no"),
            "item_no": ref.get("item_no"),
            "subitem_no": ref.get("subitem_no"),
        })

#norm_unit2차 - cross_refs
class NormUnitCrossRefChain:
    def __init__(self, model: str = "gpt-5.1"):
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=NormUnitCrossRefOutput)

        self.prompt = PromptTemplate(
            template=CROSS_REF,
            input_variables=[
                "article_id",
                "text",
                "level",
                "para_no",
                "item_no",
                "subitem_no",
            ],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def extract(self, inp: NormUnitCrossRefInput) -> NormUnitCrossRefOutput:
        ref = inp.ref or {}
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "article_id": inp.article_id,
            "text": inp.text,
            "para_no": ref.get("para_no"),
            "item_no": ref.get("item_no"),
            "subitem_no": ref.get("subitem_no"),
            "level": inp.level or "",
        })

#pass0 chapter_semantic
class ChapterSemanticChain:
    def __init__(self, model: str = "gpt-5.1"):
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=ChapterSemanticOutput)

        self.prompt = PromptTemplate(
            template=CHAPTER_SEMANTICS,
            input_variables=["chapter_id", "chapter_name", "domain", "text"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def semantic(self, inp: ChapterSemanticInput) -> ChapterSemanticOutput:
        chain = self.prompt | self.llm | self.parser

        return chain.invoke({
            "chapter_id": inp.chapter_id,
            "chapter_name": inp.chapter_name,
            "domain": inp.domain,
            "text": inp.text,
        })


class ChapterReasoningChain:
    def __init__(self, model: str = "gpt-5.1"):
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=ChapterReasoningOutput)

        self.prompt = PromptTemplate(
            template=REASONING,
            input_variables=["chapter_id", "chapter_name", "text"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def run(self, inp: ChapterReasoningInput) -> ChapterReasoningOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "chapter_id": inp.chapter_id,
            "chapter_name": inp.chapter_name,
            "text": inp.text,
        })
