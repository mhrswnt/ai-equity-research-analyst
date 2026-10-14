"""Isolated execution of LLM-written Python: separate process, temp cwd, scrubbed env (no API keys), timeout, capped output."""
import asyncio
import sys
import tempfile

from app.core.config import get_settings

MAX_OUTPUT_CHARS = 20000
_SAFE_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")


async def run_python(code: str, timeout_s: int | None = None) -> dict:
    import os
    timeout_s = timeout_s or get_settings().sandbox_timeout_s
    env = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}
    with tempfile.TemporaryDirectory() as cwd:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code, cwd=cwd, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"returncode": -1, "stdout": "", "stderr": f"Timed out after {timeout_s}s"}
    return {
        "returncode": proc.returncode,
        "stdout": out.decode(errors="replace")[:MAX_OUTPUT_CHARS],
        "stderr": err.decode(errors="replace")[:MAX_OUTPUT_CHARS],
    }
