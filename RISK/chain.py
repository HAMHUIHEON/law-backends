from typing import List, Optional
from utils.llm import get_llm
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from RISK.models import (
    RevisionObservationOutput, RevisionObservationInput,
    AddendaObservationInput, AddendaObservationOutput,
    AnnexObservationInput, AnnexObservationOutput,
    ConsultingInsightOutput, CrossLawImpactOutput,
)
from RISK.prompt import (
    OBSERVATION_PROMPT, ADDENDA_OBSERVATION_PROMPT,
    ANNEX_OBSERVATION_PROMPT, CONSULTING_PROMPT, CROSS_LAW_PROMPT,
)

from utils.llm import DEFAULT_MODEL  # noqa: F811


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
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )

    def observe(self, inp: RevisionObservationInput) -> RevisionObservationOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "law_name": inp.law_name,
            "law_type": inp.law_type,
            "promulgated_at": inp.promulgated_at,
            "effective_at": inp.effective_at or "미지정",
            "revision_reason": inp.revision_reason,
            "revision_text": inp.revision_text,
        })


class AddendaObservationChain:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=AddendaObservationOutput)
        self.prompt = PromptTemplate(
            template=ADDENDA_OBSERVATION_PROMPT,
            input_variables=["law_name", "law_type", "addenda_date", "addenda_text"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )

    def observe(self, inp: AddendaObservationInput) -> AddendaObservationOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke(inp.model_dump())


class AnnexObservationChain:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=AnnexObservationOutput)
        self.prompt = PromptTemplate(
            template=ANNEX_OBSERVATION_PROMPT,
            input_variables=["annex_id", "title", "content"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )

    def observe(self, inp: AnnexObservationInput) -> AnnexObservationOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke(inp.model_dump())


class ConsultingInsightChain:
    """관측 결과 → 컨설팅 인사이트 도출."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=ConsultingInsightOutput)
        self.prompt = PromptTemplate(
            template=CONSULTING_PROMPT,
            input_variables=[
                "law_name", "law_type", "promulgated_at", "effective_at",
                "observed_changes_json", "addenda_summary", "risk_signals_json",
            ],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )

    def analyze(
        self,
        law_name: str,
        law_type: str,
        promulgated_at: str,
        effective_at: str,
        observed_changes_json: str,
        addenda_summary: str,
        risk_signals_json: str,
    ) -> ConsultingInsightOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "law_name": law_name,
            "law_type": law_type,
            "promulgated_at": promulgated_at,
            "effective_at": effective_at,
            "observed_changes_json": observed_changes_json,
            "addenda_summary": addenda_summary,
            "risk_signals_json": risk_signals_json,
        })


class CrossLawImpactChain:
    """외부 법령 개정 → 연동 세법 영향 분석."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.llm = get_llm(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=CrossLawImpactOutput)
        self.prompt = PromptTemplate(
            template=CROSS_LAW_PROMPT,
            input_variables=[
                "source_law", "promulgated_at", "effective_at",
                "observed_changes_json", "addenda_summary",
                "linked_tax_laws", "related_articles",
            ],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )

    def analyze(
        self,
        source_law: str,
        promulgated_at: str,
        effective_at: str,
        observed_changes_json: str,
        addenda_summary: str,
        linked_tax_laws: str,
        related_articles: str,
    ) -> CrossLawImpactOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "source_law": source_law,
            "promulgated_at": promulgated_at,
            "effective_at": effective_at,
            "observed_changes_json": observed_changes_json,
            "addenda_summary": addenda_summary,
            "linked_tax_laws": linked_tax_laws,
            "related_articles": related_articles,
        })
