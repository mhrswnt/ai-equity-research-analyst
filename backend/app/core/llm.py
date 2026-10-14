"""Single LLM factory. `LLM_<ROLE>=<provider>:<model>` in .env picks the model; the framework picks the adapter."""
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal

from app.core.config import get_settings

Role = Literal["default", "rag", "analysis", "strategy", "research", "compare"]
Framework = Literal["langchain", "llamaindex"]
PROVIDERS = ("anthropic", "openai", "gemini", "groq", "openrouter")


@dataclass(frozen=True)
class LLMAccess:
    """Who is paying for this request's LLM calls. `api_key` is only set for BYOK and is never stored or logged."""
    tier: Literal["free", "byok"]
    provider: str | None = None
    model: str | None = None
    api_key: str | None = field(default=None, repr=False)


# Set per request by core.access; a request's tasks/threads copy it, concurrent requests never see each other's.
current_access: ContextVar[LLMAccess | None] = ContextVar("current_access", default=None)


def parse_spec(spec: str) -> tuple[str, str]:
    provider, sep, model = spec.partition(":")
    provider = provider.strip().lower()
    if not sep or not model.strip() or provider not in PROVIDERS:
        raise ValueError(f"Invalid LLM spec '{spec}'. Expected '<provider>:<model>' with provider in {PROVIDERS}.")
    return provider, model.strip()


def resolve_spec(role: Role, override: str | None = None) -> str:
    s = get_settings()
    return override or getattr(s, f"llm_{role}", None) or s.llm_default


def get_llm(role: Role, framework: Framework, override: str | None = None):
    """Build the LLM for a role. A request-scoped `current_access` (free allowlist model or BYOK key) wins over
    `.env` role defaults and over `override`, so callers can never pick arbitrary models on operator keys."""
    access = current_access.get()
    if access is not None and access.provider:
        provider, model, api_key = access.provider, access.model, access.api_key
    else:
        provider, model = parse_spec(resolve_spec(role, None if access else override))
        api_key = None
    build = _langchain if framework == "langchain" else _llamaindex
    return build(provider, model, get_settings(), api_key)


def _langchain(provider: str, model: str, s, api_key: str | None):
    key = {"api_key": api_key} if api_key else {}  # BYOK key goes straight to the constructor, never os.environ
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, temperature=s.llm_temperature, **key)
    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model, temperature=s.llm_temperature, **key)
    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as e:
            raise RuntimeError("pip install langchain-anthropic to use Anthropic with LangChain") from e
        return ChatAnthropic(model=model, temperature=s.llm_temperature, max_tokens=s.llm_max_tokens, **key)
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise RuntimeError("pip install langchain-openai to use OpenAI/OpenRouter with LangChain") from e
    if provider == "openai":
        return ChatOpenAI(model=model, temperature=s.llm_temperature, **key)
    return ChatOpenAI(model=model, temperature=s.llm_temperature, base_url="https://openrouter.ai/api/v1",
                      api_key=api_key or s.openrouter_api_key)


def _llamaindex(provider: str, model: str, s, api_key: str | None):
    key = {"api_key": api_key} if api_key else {}
    if provider == "anthropic":
        from llama_index.llms.anthropic import Anthropic
        return _lenient(Anthropic)(model=model, max_tokens=s.llm_max_tokens, **key)
    if provider == "openai":
        from llama_index.llms.openai import OpenAI
        return _lenient(OpenAI)(model=model, max_tokens=s.llm_max_tokens, **key)
    if provider == "groq":
        from llama_index.llms.groq import Groq
        return Groq(model=model, max_tokens=s.llm_max_tokens, **key)
    if provider == "gemini":
        from llama_index.llms.google_genai import GoogleGenAI
        return GoogleGenAI(model=model, max_tokens=s.llm_max_tokens, **key)
    from llama_index.llms.openrouter import OpenRouter
    return OpenRouter(model=model, max_tokens=s.llm_max_tokens, **key)


def _lenient(llm_cls):
    """LlamaIndex's Anthropic/OpenAI wrappers raise for model ids newer than the installed package knows. BYOK users
    type whatever model they have, so fall back to generic metadata instead of failing before the request is sent."""
    from llama_index.core.base.llms.types import LLMMetadata

    class AnyModel(llm_cls):
        @property
        def metadata(self) -> LLMMetadata:
            try:
                return super().metadata
            except ValueError:
                return LLMMetadata(context_window=200_000, num_output=self.max_tokens or 4096, is_chat_model=True,
                                   is_function_calling_model=True, model_name=self.model)

    return AnyModel
