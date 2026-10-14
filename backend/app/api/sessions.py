from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import session_id
from app.core import access
from app.core.config import get_settings
from app.services import sessions

router = APIRouter(tags=["sessions"])


@router.post("/sessions", status_code=201)
def create_session(request: Request):
    access.check_rate_limit("session", access.client_ip(request), get_settings().session_create_limit_per_hour)
    return sessions.create()


@router.delete("/sessions/{sid}", status_code=204)
def end_session(sid: str, current: str = Depends(session_id)):
    """Wipes the caller's session: documents, vectors, everything."""
    if sid != current:
        raise HTTPException(404, "Session not found")
    sessions.delete(sid)
