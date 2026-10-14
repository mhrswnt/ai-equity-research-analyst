import asyncio

import pytest
from fastapi import HTTPException

from app.core import access, tasks
from app.core.config import get_settings
from app.core.llm import current_access
from app.core.security import redact
from tests.conftest import BYOK_KEY, make_request


def code(exc: pytest.ExceptionInfo) -> tuple[int, str]:
    return exc.value.status_code, exc.value.detail["code"]


def test_free_tier_defaults_and_allowlist():
    assert access.parse_access(make_request()).tier == "free"
    ok = access.parse_access(make_request({"X-LLM-Provider": "groq", "X-LLM-Model": "qwen/qwen3.8-27b"}))
    assert (ok.tier, ok.provider, ok.model, ok.api_key) == ("free", "groq", "qwen/qwen3.8-27b", None)
    with pytest.raises(HTTPException) as e:
        access.parse_access(make_request({"X-LLM-Provider": "anthropic", "X-LLM-Model": "claude-opus-5-5"}))
    assert code(e) == (403, "model_not_free")


def test_byok_parsing(byok):
    a = access.parse_access(make_request(byok))
    assert (a.tier, a.provider, a.model, a.api_key) == ("byok", "anthropic", "claude-sonnet-5-5", BYOK_KEY)
    default_model = access.parse_access(make_request({"X-LLM-Provider": "Gemini", "X-LLM-Api-Key": " key-123456789 "}))
    assert default_model.model == access.DEFAULT_BYOK_MODEL["gemini"] and default_model.api_key == "key-123456789"


@pytest.mark.parametrize("headers,expected", [
    ({"X-LLM-Api-Key": "k" * 20}, "invalid_provider"),
    ({"X-LLM-Api-Key": "k" * 20, "X-LLM-Provider": "nope"}, "invalid_provider"),
    ({"X-LLM-Api-Key": "short", "X-LLM-Provider": "groq"}, "invalid_key"),
    ({"X-LLM-Api-Key": "k" * 600, "X-LLM-Provider": "groq"}, "invalid_key"),
    ({"X-LLM-Api-Key": "has space inside!", "X-LLM-Provider": "groq"}, "invalid_key"),
    ({"X-LLM-Api-Key": "k" * 20, "X-LLM-Provider": "openrouter"}, "model_required"),
])
def test_byok_validation(headers, expected):
    with pytest.raises(HTTPException) as e:
        access.parse_access(make_request(headers))
    assert e.value.status_code == 400 and e.value.detail["code"] == expected


def test_complex_tasks_need_byok_on_free_tier(byok, monkeypatch):
    with pytest.raises(HTTPException) as e:
        access.authorize(make_request(), "complex")
    assert code(e) == (402, "byok_required")
    assert access.authorize(make_request(byok), "complex").tier == "byok"
    assert access.authorize(make_request(), "basic").tier == "free"
    monkeypatch.setattr(get_settings(), "complex_tasks_require_byok", False)
    assert access.authorize(make_request(), "complex").tier == "free"


def test_authorize_publishes_access_for_get_llm(byok):
    assert current_access.get() is None
    access.authorize(make_request(byok), "basic")
    assert current_access.get().api_key == BYOK_KEY


def test_rate_limit_sliding_window():
    for t in (0, 1, 2):
        access.check_rate_limit("free", "ip", 3, window_s=100, now=t)
    with pytest.raises(HTTPException) as e:
        access.check_rate_limit("free", "ip", 3, window_s=100, now=10)
    assert code(e) == (429, "rate_limited") and e.value.headers["Retry-After"] == "90"
    access.check_rate_limit("free", "other-ip", 3, window_s=100, now=10)       # per-IP
    access.check_rate_limit("byok", "ip", 3, window_s=100, now=10)             # per-tier
    access.check_rate_limit("free", "ip", 3, window_s=100, now=101)            # oldest hit aged out
    access.reset_rate_limits()
    access.check_rate_limit("free", "ip", 1, now=5)


def test_check_rate_limit_uses_monotonic_clock_by_default():
    access.check_rate_limit("free", "clock-ip", 1)
    with pytest.raises(HTTPException):
        access.check_rate_limit("free", "clock-ip", 1)


def test_authorize_enforces_per_tier_limits(byok, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "free_rate_limit_per_hour", 1)
    monkeypatch.setattr(s, "byok_rate_limit_per_hour", 2)
    access.authorize(make_request(), "basic")
    with pytest.raises(HTTPException) as e:
        access.authorize(make_request(), "basic")
    assert e.value.status_code == 429
    access.authorize(make_request(byok), "basic")
    access.authorize(make_request(byok), "basic")
    with pytest.raises(HTTPException):
        access.authorize(make_request(byok), "basic")


def test_client_ip(monkeypatch):
    assert access.client_ip(make_request()) == "1.2.3.4"
    assert access.client_ip(make_request(client=None)) == "unknown"
    assert access.client_ip(make_request({"X-Forwarded-For": "9.9.9.9"})) == "1.2.3.4"  # not trusted by default
    monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)
    assert access.client_ip(make_request({"X-Forwarded-For": "9.9.9.9, 8.8.8.8"})) == "9.9.9.9"
    assert access.client_ip(make_request()) == "1.2.3.4"


async def test_gate_dependency(byok):
    assert (await access.gate("basic")(make_request(byok))).tier == "byok"
    with pytest.raises(HTTPException):
        await access.gate("complex")(make_request())


async def test_concurrent_requests_never_share_keys():
    seen = {}

    async def request(name, key):
        access.authorize(make_request({"X-LLM-Provider": "groq", "X-LLM-Api-Key": key}, client=(name, 1)), "basic")
        await asyncio.sleep(0.01)  # let the other request interleave
        seen[name] = current_access.get().api_key

    await asyncio.gather(*(asyncio.create_task(request(n, f"key-for-{n}-xxxxxxx")) for n in ("a", "b", "c")))
    assert seen == {n: f"key-for-{n}-xxxxxxx" for n in ("a", "b", "c")}
    assert current_access.get() is None


def test_redact(byok):
    secrets = ["sk-ant-api03-abcdefghijk", "gsk_abcdefghijklmnop", "AIzaSyA-bcdefghijklmnop", "Bearer abc.def.ghi"]
    text = " | ".join(f"error with {s}" for s in secrets)
    clean = redact(text)
    assert not any(s in clean for s in secrets) and clean.count("[redacted]") == 4
    assert redact("nothing to hide") == "nothing to hide"
    access.authorize(make_request(byok), "basic")
    assert redact(f"the key {BYOK_KEY} leaked") == "the key [redacted] leaked"


def test_task_catalog_consistency():
    ids = [t.id for t in tasks.TASKS]
    assert len(ids) == len(set(ids))
    assert tasks.level_of("qa") == "basic" and tasks.level_of("strategy") == "complex"
    assert tasks.analysis_level("technical") == "basic" and tasks.analysis_level("custom") == "complex"
    assert {f"analysis_{t}" for t in ("price_summary", "technical", "compare", "backtest", "custom")} <= set(ids)


@pytest.mark.parametrize("provider", ["anthropic", "openai", "gemini", "groq", "openrouter"])
def test_every_provider_is_accepted_for_byok(provider):
    model = "vendor/model" if provider == "openrouter" else None  # openrouter has no default model
    a = access.parse_access(make_request({"X-LLM-Provider": provider, "X-LLM-Api-Key": "k" * 20,
                                          **({"X-LLM-Model": model} if model else {})}))
    assert a.tier == "byok" and a.provider == provider and a.model
