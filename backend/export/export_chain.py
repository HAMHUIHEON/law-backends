from langchain_core.output_parsers import PydanticOutputParser
from export.models_export import ExportAOutput
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate,PromptTemplate
from typing import List, Optional, Dict
from export.models_export import (ExportAInput, ExportAExecSummary,ExportAOutput,
                                  ExportBExecSummary,ExportBInput,ExportBOutput,
                                  ExportCExecSummary,ExportCInput,ExportCOutput)
from export.prompt import A, B, EXPORT_C_PROMPT, PARTIAL_PREFIX, B_PARTIAL_PREFIX
import json

#A
class ExportAChain:
    def __init__(self, model: str = "gpt-5.1"):
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=ExportAOutput)

        self.prompt = PromptTemplate(
            template=A,  # 너가 정의한 A 프롬프트 문자열
            input_variables=["narrative_json"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )

    def run(self, inp: ExportAInput) -> ExportAOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "narrative_json": json.dumps(inp.narrative_json, ensure_ascii=False, indent=2),
        })
    
#B
class ExportBChain:
    def __init__(self, model: str = "gpt-5.1", prompt_template: str = B):
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=ExportBOutput)

        self.prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["narrative_json", "issue_frame"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )

    def run(self, inp: ExportBInput) -> ExportBOutput:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({
            "narrative_json": json.dumps(inp.narrative_json, ensure_ascii=False, indent=2),
            "issue_frame": json.dumps(inp.issue_frame, ensure_ascii=False, indent=2),
        })



# C
class ExportCChain:
    def __init__(
        self,
        model: str = "gpt-5.1",
        prompt_template: str = EXPORT_C_PROMPT,
    ):
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=ExportCOutput)

        self.prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["issue_logic_list", "block_texts"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def run(self, inp: ExportCInput) -> ExportCOutput:
        payload = {
            "issue_logic_list": json.dumps([item.model_dump() for item in inp.issue_logic_list], ensure_ascii=False, indent=2),
            "block_texts": json.dumps(inp.block_texts, ensure_ascii=False, indent=2),
        }

        # 1) parser 없이 LLM raw 받기
        msg = (self.prompt | self.llm).invoke(payload)
        raw = msg.content

        # raw가 None/빈문자/ "null" 인지 확인
        if raw is None:
            raise RuntimeError("LLM returned None content")
        if not str(raw).strip():
            raise RuntimeError("LLM returned empty content")

        # 디버그 저장(원하면)
        # Path("debug_last_exportC.txt").write_text(str(raw), encoding="utf-8")

        # 2) 이제 parser
        return self.parser.parse(raw)


