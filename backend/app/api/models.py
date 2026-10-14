from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from app.core import access, tasks
from app.core.config import get_settings
from app.core.llm import PROVIDERS, get_llm
from app.core.security import redact

router = APIRouter(tags=["models"])


@router.get("/models")
def catalog():
    s = get_settings()
    return {
        "free_models": s.free_models,
        "byok_providers": {p: {"default": access.DEFAULT_BYOK_MODEL.get(p), "suggested": access.SUGGESTED_BYOK_MODELS[p]}
                           for p in PROVIDERS},
        "headers": {"provider": "X-LLM-Provider", "api_key": "X-LLM-Api-Key", "model": "X-LLM-Model"},
        "complex_tasks_require_byok": s.complex_tasks_require_byok,
    }


@router.get("/tasks")
def task_catalog():
    s = get_settings()
    return [{**asdict(t), "max_docs": t.max_docs if t.max_docs is not None else s.max_docs_per_session,
             "free_allowed": t.level == "basic" or not s.complex_tasks_require_byok} for t in tasks.TASKS]


@router.post("/models/validate")
async def validate_key(request: Request):
    """Cheap 1-call check that a BYOK key/model works, so the UI can confirm before a real task."""
    if access.authorize(request, "basic").tier != "byok":
        raise HTTPException(400, {"code": "byok_required", "message": "Send X-LLM-Provider, X-LLM-Api-Key and X-LLM-Model."})
    try:
        await get_llm("default", "llamaindex").acomplete("Reply with OK")
    except Exception as e:
        raise HTTPException(400, {"code": "key_rejected", "message": redact(f"{type(e).__name__}: {e}")[:300]})
    return {"ok": True}
