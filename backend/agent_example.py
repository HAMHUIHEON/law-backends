import os
import json
from dotenv import load_dotenv
load_dotenv('../.env')

from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain.tools import tool
from db.graph_search import LegalGraphSearch


@tool
def search_similar_issues(query: str) -> str:
    """자연어 쟁점으로 의미적으로 유사한 판례를 검색합니다."""
    s = LegalGraphSearch()
    results = s.search_similar_issues(query, top_k=5)
    s.close()
    return json.dumps(results, ensure_ascii=False, indent=2)


@tool
def analyze_winning_patterns(query: str) -> str:
    """유사 쟁점 판례의 승소/패소 패턴과 자주 인용된 법령을 분석합니다."""
    s = LegalGraphSearch()
    result = s.analyze_winning_patterns(query, top_k=10)
    s.close()
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool
def get_statute_cases(statute_name: str) -> str:
    """특정 법령을 인용한 판례 목록을 시계열순으로 반환합니다."""
    s = LegalGraphSearch()
    results = s.get_statute_cases(statute_name)
    s.close()
    return json.dumps(results, ensure_ascii=False, indent=2)


llm = ChatOpenAI(model="gpt-4o", temperature=0)
tools = [search_similar_issues, analyze_winning_patterns, get_statute_cases]

prompt = ChatPromptTemplate.from_messages([
    ("system", (
        "당신은 세무/행정소송 전문 AI 어시스턴트입니다. "
        "판례 데이터베이스를 활용해 정확한 법리 분석을 제공하세요. "
        "반드시 도구를 사용하여 실제 판례 데이터를 근거로 답변하세요."
    )),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

print("=" * 60)
print("질문: 국제조세조정법 관련 특수관계자 거래 판례를 찾고, 납세자 승소 패턴을 분석해줘")
print("=" * 60)

result = executor.invoke({
    "input": "국제조세조정법 관련 특수관계자 거래 판례를 찾고, 납세자 승소 패턴을 분석해줘"
})

print("\n" + "=" * 60)
print("[최종 답변]")
print("=" * 60)
print(result["output"])
