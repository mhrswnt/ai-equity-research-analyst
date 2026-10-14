from fastapi import Header, HTTPException

from app.services import sessions


def session_id(x_session_id: str | None = Header(None)) -> str:
    """Require a live session (X-Session-Id header); refreshes its idle timer."""
    if not x_session_id or not sessions.touch(x_session_id):
        raise HTTPException(401, detail={"code": "invalid_session",
                                         "message": "Missing, unknown or expired X-Session-Id. Create one with POST /sessions."})
    return x_session_id
