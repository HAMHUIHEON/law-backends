"""
중앙 LLM 팩토리 — A안: Claude LLM + OpenAI 임베딩

우선순위:
  1. ANTHROPIC_API_KEY 있으면 → ChatAnthropic (claude-sonnet-4-6) with_fallbacks(ChatOpenAI)
  2. 없으면 → ChatOpenAI (gpt-4.1) 직접 사용

크레딧 부족(400), 인증 오류(401), 과부하(529) 시 GPT-4.1로 폴백.
임베딩(Chroma EmbeddingFunction)은 항상 OpenAI 유지.
"""
from __future__ import annotations
import os

DEFAULT_MODEL = "claude-sonnet-4-6"
_FALLBACK_MODEL = "gpt-4.1"


def get_llm(model: str = DEFAULT_MODEL, temperature: float = 0):
    """
    LLM 반환.
    - ANTHROPIC_API_KEY 있으면 Claude 우선, 크레딧/인증/과부하 오류 시 GPT-4.1 폴백.
    - ANTHROPIC_API_KEY 없으면 GPT-4.1 직접 사용.
    """
    from langchain_openai import ChatOpenAI

    openai_llm = ChatOpenAI(model=_FALLBACK_MODEL, temperature=temperature)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not anthropic_key:
        return openai_llm

    from langchain_anthropic import ChatAnthropic
    from anthropic import BadRequestError, AuthenticationError, APIStatusError

    claude_llm = ChatAnthropic(
        model=model,
        temperature=temperature,
        api_key=anthropic_key,
    )
    # 크레딧 부족(400) · 인증 실패(401) · 서버 과부하(529) 만 폴백
    # 일반 Exception은 캐치하지 않아 Claude를 최대한 직접 사용
    return claude_llm.with_fallbacks(
        [openai_llm],
        exceptions_to_handle=(BadRequestError, AuthenticationError, APIStatusError),
    )
