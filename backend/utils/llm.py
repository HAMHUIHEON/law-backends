import os

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.runnables import Runnable

# Claude를 기본으로, 실패(400/rate limit/네트워크 등) 시 GPT로 자동 폴백.
# Claude 최신 모델(Sonnet 5/Opus 4.8 등)은 temperature=0을 400으로 거부하지만,
# 이 프로젝트의 모든 에이전트는 재현성을 위해 temperature=0을 사용한다.
# claude-sonnet-4-6은 temperature=0을 허용하며 near-Opus 품질 + 1M 컨텍스트라 기본으로 채택.
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
DEFAULT_OPENAI_MODEL = "gpt-4.1"

# 하위 호환: 기존 모듈들이 `from utils.llm import DEFAULT_MODEL`로 임포트한다.
DEFAULT_MODEL = DEFAULT_CLAUDE_MODEL


def _make_openai(model: str, temperature: float, **kwargs) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        **kwargs,
    )


def _make_claude(model: str, temperature: float, **kwargs) -> ChatAnthropic:
    # ChatAnthropic는 max_tokens가 필수 → 법률 보고서 생성용으로 넉넉히 기본값 지정.
    kwargs.setdefault("max_tokens", 8192)
    return ChatAnthropic(
        model=model,
        temperature=temperature,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        **kwargs,
    )


def get_llm(model: str = DEFAULT_MODEL, temperature: float = 0, **kwargs) -> Runnable:
    """Claude를 우선 사용하고 실패 시 GPT로 폴백하는 LLM을 반환한다.

    - `model`이 "gpt..."이면 그 모델을 폴백 GPT 모델로, Claude는 기본 모델로 사용.
    - `model`이 "claude..."이면 그 모델을 Claude 기본 모델로 사용.
    - 반환값은 RunnableWithFallbacks라 `.invoke()`와 `prompt | llm` 모두 동작한다.
    """
    claude_model = model if model.startswith("claude") else DEFAULT_CLAUDE_MODEL
    openai_model = model if model.startswith("gpt") else DEFAULT_OPENAI_MODEL

    primary = _make_claude(claude_model, temperature, **kwargs)
    # openai에는 anthropic 전용 kwargs(max_tokens 등)를 넘기지 않도록 분리.
    openai_kwargs = {k: v for k, v in kwargs.items() if k != "max_tokens"}
    fallback = _make_openai(openai_model, temperature, **openai_kwargs)

    return primary.with_fallbacks([fallback])
