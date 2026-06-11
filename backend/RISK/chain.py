#revision
from typing import List, Optional, Dict
import json
from utils.llm import get_llm, DEFAULT_MODEL
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from RISK.models import (RevisionObservationOutput,RevisionObservationInput,
                         AddendaObservationInput,AddendaObservationOutput,
                         AnnexObservationInput,AnnexObservationOutput)

from RISK.prompt import OBSERVATION_PROMPT,ADDENDA_OBSERVATION_PROMPT,ANNEX_OBSERVATION_PROMPT


class RevisionObservationChain:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=RevisionObservationOutput)

        self.prompt = PromptTemplate(
            template=OBSERVATION_PROMPT,
            input_variables=[
                "law_name", "law_type", "promulgated_at", "effective_at",
                "revision_reason", "revision_text"
            ],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def observe(self, inp: RevisionObservationInput) -> RevisionObservationOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "law_name": inp.law_name,
            "law_type": inp.law_type,
            "promulgated_at": inp.promulgated_at,
            "effective_at": inp.effective_at,
            "revision_reason": inp.revision_reason,
            "revision_text": inp.revision_text,
        })



#부칙
class AddendaObservationChain:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0)
        self.parser = PydanticOutputParser(
            pydantic_object=AddendaObservationOutput
        )

        self.prompt = PromptTemplate(
            template=ADDENDA_OBSERVATION_PROMPT,
            input_variables=[
                "law_name",
                "law_type",
                "addenda_date",
                "addenda_text",
            ],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def observe(self, inp: AddendaObservationInput) -> AddendaObservationOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke(inp.dict())


#별표
class AnnexObservationChain:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0)
        self.parser = PydanticOutputParser(
            pydantic_object=AnnexObservationOutput
        )

        self.prompt = PromptTemplate(
            template=ANNEX_OBSERVATION_PROMPT,
            input_variables=["annex_id", "title", "content"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def observe(self, inp: AnnexObservationInput) -> AnnexObservationOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke(inp.model_dump())
