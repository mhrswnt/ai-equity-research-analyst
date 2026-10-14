"""Anonymous, ephemeral sessions. A session is a directory `data/sessions/<id>/` with a `session.json` heartbeat;
it (and all its documents/vectors) is deleted on logout or after `session_ttl_minutes` of inactivity."""
import json
import re
import secrets
import time

from app.core.config import get_settings
from app.services import documents

SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")  # also guards against path traversal


def _meta_path(sid: str):
    return get_settings().session_dir(sid) / "session.json"


def _expires_at(last_seen: float) -> float:
    return last_seen + get_settings().session_ttl_minutes * 60


def create() -> dict:
    sid = secrets.token_hex(16)
    get_settings().session_dir(sid).mkdir(parents=True)
    now = time.time()
    _meta_path(sid).write_text(json.dumps({"created": now, "last_seen": now}))
    return {"session_id": sid, "expires_at": _expires_at(now)}


def _read(sid: str) -> dict | None:
    if not SESSION_ID_RE.match(sid) or not _meta_path(sid).exists():
        return None
    return json.loads(_meta_path(sid).read_text())


def touch(sid: str) -> bool:
    """Validate and refresh a session. Returns False if unknown or expired (expired ones are deleted)."""
    meta = _read(sid)
    if meta is None:
        return False
    now = time.time()
    if now > _expires_at(meta["last_seen"]):
        delete(sid)
        return False
    _meta_path(sid).write_text(json.dumps({**meta, "last_seen": now}))
    return True


def delete(sid: str) -> None:
    if SESSION_ID_RE.match(sid):
        documents.purge_session(sid)


def sweep_expired() -> int:
    """Delete every expired (or half-created) session directory; returns how many were removed."""
    removed = 0
    for path in get_settings().sessions_dir.iterdir():
        if not (path.is_dir() and SESSION_ID_RE.match(path.name)):
            continue
        meta = _read(path.name)
        if meta is None or time.time() > _expires_at(meta["last_seen"]):
            documents.purge_session(path.name)
            removed += 1
    return removed
