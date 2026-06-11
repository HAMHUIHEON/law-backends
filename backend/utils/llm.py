import os
from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "gpt-4.1"


def get_llm(model: str = DEFAULT_MODEL, temperature: float = 0, **kwargs) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        **kwargs,
    )
