"""Request gate: resolves who pays for the LLM (free allowlist vs BYOK header), enforces task level and rate limits.

Headers: X-LLM-Api-Key (+ X-LLM-Provider, X-LLM-Model) => BYOK. Without a key => free tier on operator keys.
The BYOK key lives only in a ContextVar for the duration of the request; it is never stored or logged."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.config import get_settings
from app.core.llm import PROVIDERS, LLMAccess, current_access
from app.core.tasks import Level

DEFAULT_BYOK_MODEL = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-4o", "gemini": "gemini-2.5-pro",
                      "groq": "qwen/qwen3.8-27b"}
SUGGESTED_BYOK_MODELS = {
    "anthropic": ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-4-5-20251001"],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini"],
    "gemini": ["gemini-2.5-pro", "gemini-2.5-flash"],
    "groq": ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"],
    # OpenRouter has no default: the user picks any "<vendor>/<model>" id from their account
    "openrouter": ["anthropic/claude-sonnet-4.5", "openai/gpt-4o", "google/gemini-2.5-pro"],
}
KEY_MIN_LEN, KEY_MAX_LEN = 8, 512

_hits: dict[str, deque] = defaultdict(deque)


def _error(status: int, code: str, message: str, headers: dict | None = None) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message}, headers=headers)


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(bucket: str, ip: str, limit: int, window_s: int = 3600, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    hits = _hits[f"{bucket}:{ip}"]
    while hits and now - hits[0] >= window_s:
        hits.popleft()
    if len(hits) >= limit:
        retry = max(1, int(window_s - (now - hits[0])))
        raise _error(429, "rate_limited", f"Rate limit of {limit}/hour reached for the {bucket} tier.",
                     {"Retry-After": str(retry)})
    hits.append(now)


def reset_rate_limits() -> None:
    _hits.clear()


def parse_access(request: Request) -> LLMAccess:
    s = get_settings()
    key = request.headers.get("x-llm-api-key")
    provider = (request.headers.get("x-llm-provider") or "").strip().lower()
    model = (request.headers.get("x-llm-model") or "").strip()
    if key is None:  # free tier on operator keys
        if not provider and not model:
            return LLMAccess(tier="free")
        spec = f"{provider}:{model}"
        if spec not in s.free_models:
            raise _error(403, "model_not_free", f"'{spec}' is not a free model. Free models: {s.free_models}. "
                                               "Provide your own key to use other models.")
        return LLMAccess(tier="free", provider=provider, model=model)
    key = key.strip()
    if provider not in PROVIDERS:
        raise _error(400, "invalid_provider", f"X-LLM-Provider must be one of {list(PROVIDERS)}.")
    if not KEY_MIN_LEN <= len(key) <= KEY_MAX_LEN or any(c.isspace() or ord(c) < 32 for c in key):
        raise _error(400, "invalid_key", "X-LLM-Api-Key is malformed.")
    model = model or DEFAULT_BYOK_MODEL.get(provider, "")
    if not model:
        raise _error(400, "model_required", f"X-LLM-Model is required for provider '{provider}'.")
    return LLMAccess(tier="byok", provider=provider, model=model, api_key=key)


def authorize(request: Request, level: Level) -> LLMAccess:
    """Resolve + enforce access for a task of the given level, then publish it for get_llm()."""
    s = get_settings()
    access = parse_access(request)
    if access.tier == "free" and level == "complex" and s.complex_tasks_require_byok:
        raise _error(402, "byok_required", "This task needs a stronger model. Provide your own API key "
                                           "(X-LLM-Provider, X-LLM-Api-Key, X-LLM-Model).")
    limit = s.free_rate_limit_per_hour if access.tier == "free" else s.byok_rate_limit_per_hour
    check_rate_limit(access.tier, client_ip(request), limit)
    current_access.set(access)
    return access


def gate(level: Level):
    """FastAPI dependency factory: `dependencies=[Depends(gate("basic"))]`."""
    async def dependency(request: Request) -> LLMAccess:
        return authorize(request, level)
    return dependency
