import os

import pytest

from app.core import config, llm
from app.core.llm import LLMAccess, current_access
from tests.conftest import Recorder


def test_settings_properties_and_env_export(monkeypatch, tmp_path):
    monkeypatch.setenv("TAVILY_API_KEY", "tav-test")
    config.get_settings.cache_clear()
    try:
        s = config.get_settings()
        s.data_dir = tmp_path / "d"
        assert s.sessions_dir == tmp_path / "d" / "sessions"
        assert s.chroma_dir == tmp_path / "d" / "chroma"
        assert s.session_dir("abc") == tmp_path / "d" / "sessions" / "abc"
        assert os.environ["TAVILY_API_KEY"]
    finally:
        config.get_settings.cache_clear()
        config.get_settings()


def test_get_settings_exports_set_keys_only(monkeypatch):
    config.get_settings.cache_clear()
    monkeypatch.setenv("HF_TOKEN", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key")
    try:
        s = config.get_settings()
        assert s.google_api_key == "g-key" and os.environ["GOOGLE_API_KEY"] == "g-key"
        assert s.free_models and s.complex_tasks_require_byok is True
    finally:
        config.get_settings.cache_clear()


def test_parse_spec():
    assert llm.parse_spec("groq:qwen/qwen3.8-27b") == ("groq", "qwen/qwen3.8-27b")
    assert llm.parse_spec(" Gemini : gemini-2.5-flash ") == ("gemini", "gemini-2.5-flash")
    for bad in ("nomodel", "foo:bar", "groq:", "groq:  "):
        with pytest.raises(ValueError):
            llm.parse_spec(bad)


def test_resolve_spec(monkeypatch):
    s = config.get_settings()
    assert llm.resolve_spec("rag", "groq:x") == "groq:x"
    assert llm.resolve_spec("rag") == s.llm_rag
    monkeypatch.setattr(s, "llm_rag", "")
    assert llm.resolve_spec("rag") == s.llm_default


def test_access_repr_hides_key():
    assert "secret-key" not in repr(LLMAccess(tier="byok", provider="groq", model="m", api_key="secret-key"))


@pytest.mark.parametrize("spec,module,cls", [
    ("gemini:g-model", "langchain_google_genai", "ChatGoogleGenerativeAI"),
    ("groq:q-model", "langchain_groq", "ChatGroq"),
    ("anthropic:a-model", "langchain_anthropic", "ChatAnthropic"),
    ("openai:oa-model", "langchain_openai", "ChatOpenAI"),
    ("openrouter:o-model", "langchain_openai", "ChatOpenAI"),
])
def test_langchain_adapters_use_server_keys(fake_module, spec, module, cls):
    fake_module(module, **{cls: Recorder})
    out = llm.get_llm("rag", "langchain", spec)
    assert out.kwargs["model"] == spec.split(":")[1]
    if spec.startswith("openrouter"):
        assert out.kwargs["base_url"].startswith("https://openrouter.ai")
        assert out.kwargs["api_key"] == config.get_settings().openrouter_api_key
    else:
        assert "base_url" not in out.kwargs
        assert "api_key" not in out.kwargs  # library reads the server key from the environment


@pytest.mark.parametrize("provider,module,cls", [
    ("gemini", "langchain_google_genai", "ChatGoogleGenerativeAI"),
    ("groq", "langchain_groq", "ChatGroq"),
    ("anthropic", "langchain_anthropic", "ChatAnthropic"),
    ("openai", "langchain_openai", "ChatOpenAI"),
    ("openrouter", "langchain_openai", "ChatOpenAI"),
])
def test_langchain_byok_key_passed_explicitly(fake_module, provider, module, cls):
    fake_module(module, **{cls: Recorder})
    current_access.set(LLMAccess(tier="byok", provider=provider, model="user-model", api_key="user-key"))
    out = llm.get_llm("rag", "langchain", "groq:ignored-override")
    assert out.kwargs["api_key"] == "user-key" and out.kwargs["model"] == "user-model"


@pytest.mark.parametrize("spec,module", [("anthropic:a", "langchain_anthropic"), ("openai:o", "langchain_openai"),
                                         ("openrouter:o", "langchain_openai")])
def test_langchain_missing_optional_packages(block_import, spec, module):
    block_import(module)
    with pytest.raises(RuntimeError, match="pip install"):
        llm.get_llm("rag", "langchain", spec)


@pytest.mark.parametrize("provider,module,cls", [
    ("anthropic", "llama_index.llms.anthropic", "Anthropic"),
    ("openai", "llama_index.llms.openai", "OpenAI"),
    ("groq", "llama_index.llms.groq", "Groq"),
    ("gemini", "llama_index.llms.google_genai", "GoogleGenAI"),
    ("openrouter", "llama_index.llms.openrouter", "OpenRouter"),
])
def test_llamaindex_adapters(fake_module, provider, module, cls):
    fake_module(module, **{cls: Recorder})
    out = llm.get_llm("analysis", "llamaindex", f"{provider}:m1")
    assert out.kwargs["model"] == "m1" and "api_key" not in out.kwargs
    assert out.kwargs["max_tokens"] == config.get_settings().llm_max_tokens
    current_access.set(LLMAccess(tier="byok", provider=provider, model="m2", api_key="k"))
    byok = llm.get_llm("analysis", "llamaindex")
    assert byok.kwargs["api_key"] == "k" and byok.kwargs["model"] == "m2"


def test_free_access_ignores_override_and_uses_role_default(fake_module):
    fake_module("llama_index.llms.groq", Groq=Recorder)
    current_access.set(LLMAccess(tier="free"))
    out = llm.get_llm("analysis", "llamaindex", "anthropic:expensive-override")
    assert out.kwargs["model"] == config.get_settings().llm_analysis.split(":")[1]


def test_free_access_with_allowlisted_model_has_no_key(fake_module):
    fake_module("llama_index.llms.groq", Groq=Recorder)
    current_access.set(LLMAccess(tier="free", provider="groq", model="free-model"))
    out = llm.get_llm("analysis", "llamaindex")
    assert out.kwargs["model"] == "free-model" and "api_key" not in out.kwargs


@pytest.mark.parametrize("provider,module,cls", [
    ("anthropic", "langchain_anthropic", "ChatAnthropic"), ("openai", "langchain_openai", "ChatOpenAI"),
    ("openrouter", "langchain_openai", "ChatOpenAI")])
def test_byok_does_not_touch_environment(fake_module, provider, module, cls):
    fake_module(module, **{cls: Recorder})
    before = dict(os.environ)
    current_access.set(LLMAccess(tier="byok", provider=provider, model="m", api_key="user-secret-key"))
    llm.get_llm("rag", "langchain")
    assert dict(os.environ) == before and "user-secret-key" not in os.environ.values()


@pytest.mark.parametrize("provider,known", [("anthropic", "claude-opus-4-5-20251101"), ("openai", "gpt-4o")])
def test_llamaindex_accepts_model_ids_newer_than_the_installed_package(provider, known):
    pytest.importorskip(f"llama_index.llms.{provider}")
    unknown = llm._llamaindex(provider, "model-from-the-future-9", config.get_settings(), "sk-test-key-1234567")
    assert unknown.metadata.model_name == "model-from-the-future-9" and unknown.metadata.is_function_calling_model
    assert llm._llamaindex(provider, known, config.get_settings(), "sk-test-key-1234567").metadata.context_window > 0


@pytest.mark.parametrize("framework", ["langchain", "llamaindex"])
@pytest.mark.parametrize("provider", ["anthropic", "openai", "gemini", "groq", "openrouter"])
def test_real_provider_classes_accept_a_byok_key(provider, framework):
    """No fakes: proves the installed SDK wrappers take our constructor arguments (api_key=, model=)."""
    module = {"langchain": {"anthropic": "langchain_anthropic", "openai": "langchain_openai",
                            "gemini": "langchain_google_genai", "groq": "langchain_groq",
                            "openrouter": "langchain_openai"},
              "llamaindex": {"anthropic": "llama_index.llms.anthropic", "openai": "llama_index.llms.openai",
                             "gemini": "llama_index.llms.google_genai", "groq": "llama_index.llms.groq",
                             "openrouter": "llama_index.llms.openrouter"}}[framework][provider]
    pytest.importorskip(module)
    if (framework, provider) == ("llamaindex", "gemini"):
        pytest.skip("GoogleGenAI validates the key/model against the API inside its constructor (network)")
    current_access.set(LLMAccess(tier="byok", provider=provider, model="some-model", api_key="sk-test-key-1234567"))
    out = llm.get_llm("rag", framework)
    assert out is not None and "some-model" in repr(out.__dict__) + str(getattr(out, "model", ""))
