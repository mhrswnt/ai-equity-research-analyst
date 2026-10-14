import asyncio
import socket
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import analysis, compare, documents, models, research, sessions as sessions_api, strategy
from app.core.config import get_settings
from app.core.llm import PROVIDERS, parse_spec
from app.core.security import redact
from app.services import sessions


async def _sweep_loop():
    while True:
        await asyncio.to_thread(sessions.sweep_expired)
        await asyncio.sleep(get_settings().session_sweep_interval_s)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_sweep_loop())  # expire idle sessions (documents + vectors) in the background
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _is_network_error(exc: BaseException | None) -> bool:
    """True if the error or anything in its cause chain is a DNS/connection failure."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, (httpx.TransportError, socket.gaierror, ConnectionError)):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


class UpstreamErrorMiddleware:
    """Turns unhandled errors (expired key, quota, network, ...) into a JSON 502 with secrets scrubbed.

    Implemented as middleware *inside* CORSMiddleware: Starlette's catch-all exception handler sits outside it,
    so its responses would lack CORS headers and the browser could not read the reason."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def tracking_send(message):
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if started:  # response already streaming; nothing sensible to send
                raise
            text = f"{type(exc).__name__}: {exc}"
            if _is_network_error(exc):
                text = ("Network error reaching an upstream service (DNS or connection failed). "
                        f"Check your internet connection and try again. Details: {text}")
            body = {"detail": redact(text)[:1000]}
            await JSONResponse(status_code=502, content=body)(scope, receive, send)


app = FastAPI(title="AI Equity Research Assistant", lifespan=lifespan)
app.add_middleware(UpstreamErrorMiddleware)  # added first => inside CORS
app.add_middleware(
    CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"],
    allow_headers=["Content-Type", "X-Session-Id", "X-LLM-Provider", "X-LLM-Api-Key", "X-LLM-Model"],
    expose_headers=["Retry-After"],
)

for module in (sessions_api, documents, models, analysis, strategy, research, compare):
    app.include_router(module.router)


@app.get("/health", tags=["health"])
def health():
    s = get_settings()
    roles = {r: getattr(s, f"llm_{r}") for r in ("default", "rag", "analysis", "strategy", "research", "compare")}
    for spec in [*roles.values(), *s.free_models]:
        parse_spec(spec)
    keys = {p: bool(getattr(s, f"{k}_api_key")) for p, k in
            {"anthropic": "anthropic", "openai": "openai", "gemini": "google", "groq": "groq",
             "openrouter": "openrouter", "llama_cloud": "llama_cloud", "tavily": "tavily"}.items()}
    return {"status": "ok", "providers": PROVIDERS, "models": roles, "free_models": s.free_models,
            "keys_configured": keys}

