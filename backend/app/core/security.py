"""Secret redaction for anything that leaves the server in an error message."""
import re

from app.core.llm import current_access

_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),       # Anthropic / OpenAI / OpenRouter
    re.compile(r"gsk_[A-Za-z0-9]{8,}"),          # Groq
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),      # Google
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
)


def redact(text: str) -> str:
    access = current_access.get()
    if access is not None and access.api_key:
        text = text.replace(access.api_key, "[redacted]")
    for pattern in _PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text
