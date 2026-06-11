# bravo/chain_bravo.py

from utils.llm import get_llm, DEFAULT_MODEL
from langchain_core.prompts import ChatPromptTemplate,PromptTemplate
from bravo.models_bravo import (BravoKeywordInput,BravoKeywordOutput,BravoIssueCitationInput,
                                BravoIssueCitationOutput,CitationItem,CitationSource,
                                BravoIssueInput,BravoTopicInput,
                                BravoSignatureInput,BravoSignatureOutput,
                                BravoGlobalOutline,BravoIssueOutput,BravoNarrativeOutput)
from langchain_core.output_parsers import PydanticOutputParser
from utils.parsers import CleanJsonParser
from bravo.prompts import (GLOBAL_SUMMARY_TMPL,CLUSTER,
                           PASS_ZERO, NARRATIVE,KEYWORD,CITATION)

from typing import List, Optional, Dict


#pass2-Citation
class BravoIssueCitationChain:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0, timeout=60)
        self.parser = CleanJsonParser(pydantic_object=BravoIssueCitationOutput)

        self.prompt = PromptTemplate(
            template=CITATION,
            input_variables=["issue","full_text"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def extract(self, inp:BravoIssueCitationInput) -> BravoIssueCitationOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "issue": inp.issue,
            "full_text": inp.full_text,
        })

  
#pass1   
class BravoGlobalChain:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0, timeout=60)
        self.parser = CleanJsonParser(pydantic_object=BravoGlobalOutline)

        self.prompt = PromptTemplate(
            template=GLOBAL_SUMMARY_TMPL,
            input_variables=["full_text"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def summarize(self, full_text: str) -> BravoGlobalOutline:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "full_text": full_text,
        })


#pass0
class ReasoningIssueChain:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0, timeout=60)
        self.parser = CleanJsonParser(pydantic_object=BravoIssueOutput)

        self.prompt = PromptTemplate(
            template=PASS_ZERO,
            input_variables=["keywords", "full_text"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )
    def extract(self, inp: BravoIssueInput) -> BravoIssueOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "keywords": inp.keywords,
            "full_text": inp.full_text,
        })

#pass_base_b-1
from utils.llm import get_llm
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

class BravoSignatureChain:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0, timeout=60)
        self.parser = CleanJsonParser(pydantic_object=BravoSignatureOutput)

        self.prompt = PromptTemplate(
            template=CLUSTER,
            input_variables=["keywords"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions(),
            },
        )

    def cluster(self, keywords: List[str]) -> BravoSignatureOutput:
        """
        키워드 리스트 하나를 통째로 넣어서
        {대표키워드: [하위키워드...]} 구조를 받는다.
        """
        keywords_str = "\n".join(f"- {kw}" for kw in keywords)
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({"keywords": keywords_str})


#pass_base_b
class BravoKeywordChain:
    def __init__(self, model=DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0, timeout=60)
        self.parser = CleanJsonParser(pydantic_object=BravoKeywordOutput)

        self.prompt = PromptTemplate(
            template=KEYWORD,
            input_variables=["core_conflict"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions(),
            },
        )

    def extract(self, core_conflict: str) -> BravoKeywordOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({"core_conflict": core_conflict})


#pass_base_a
class BravoNarrativeChain:
    def __init__(self, model=DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0, timeout=60)
        self.parser = CleanJsonParser(pydantic_object=BravoNarrativeOutput)

        self.prompt = PromptTemplate(
            template=NARRATIVE,
            input_variables=["full_text"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def narrative(self, global_input: BravoTopicInput) -> BravoNarrativeOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "full_text": global_input.full_text,
        })
