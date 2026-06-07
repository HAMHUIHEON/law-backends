#ITCL_integrated/chain.py
from typing import List, Optional, Dict
import json
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from ITCL_integrated.prompts import (INTEGRATED_CHAPTER_SEMANTICS,
                                     INTEGRATED_REASONING,MATCH)
from ITCL_integrated.models import (IntegratedChapterSemanticInput,IntegratedChapterSemanticOutput,
                                    IntegratedChapterReasoningInput,IntegratedChapterReasoningOutput,
                                    IntegratedIssueReasoning,ChapterAlignmentInput,ChapterAlignmentOutput,
                                    AlignmentItem,)
#시멘틱
class IntegratedChapterSemanticChain:
    def __init__(self, model: str = "gpt-5.1"):
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.parser = PydanticOutputParser(
            pydantic_object=IntegratedChapterSemanticOutput
        )

        self.prompt = PromptTemplate(
            template=INTEGRATED_CHAPTER_SEMANTICS,
            input_variables=["chapter_id", "chapter_name", "domain", "text"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def semantic(self, inp: IntegratedChapterSemanticInput):
        chain = self.prompt | self.llm | self.parser
        return chain.invoke(inp.model_dump())
#리즈닝
class IntegratedChapterReasoningChain:
    def __init__(self, model: str = "gpt-5.1"):
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=IntegratedChapterReasoningOutput)

        self.prompt = PromptTemplate(
            template=INTEGRATED_REASONING,
            input_variables=["chapter_id", "chapter_name", "text"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def run(self, inp: IntegratedChapterReasoningInput) -> IntegratedChapterReasoningOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "chapter_id": inp.chapter_id,
            "chapter_name": inp.chapter_name,
            "text": inp.text,
        })


#얼라이닝
def _dump_list(items):
    out = []
    for x in items:
        if hasattr(x, "model_dump"):
            out.append(x.model_dump())
        else:
            out.append(x)
    return out

class IntegratedChapterAlignmentChain:
    def __init__(self, model: str = "gpt-5.1"):
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=ChapterAlignmentOutput)

        self.prompt = PromptTemplate(
            template=MATCH,
            input_variables=["chapter_id", "semantic_issues", "reasoning_issues"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def align(self, inp: ChapterAlignmentInput) -> ChapterAlignmentOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "chapter_id": inp.chapter_id,
            "semantic_issues": json.dumps(_dump_list(inp.semantic_issues), ensure_ascii=False, indent=2),
            "reasoning_issues": json.dumps(_dump_list(inp.reasoning_issues), ensure_ascii=False, indent=2),
        })
        

