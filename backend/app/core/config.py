"""Central settings. All keys, model selectors and tunables come from the root .env."""
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- provider keys ---
    google_api_key: str = ""
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    llama_cloud_api_key: str = ""
    tavily_api_key: str = ""
    hf_token: str = ""

    # --- per-role model selectors: "<provider>:<model>" ---
    llm_default: str = "anthropic:claude-opus-4-5-20251101"
    llm_rag: str = "gemini:gemini-2.5-flash"
    llm_analysis: str = "groq:qwen/qwen3.8-27b"
    llm_strategy: str = "groq:qwen/qwen3.8-27b"
    llm_research: str = "anthropic:claude-opus-4-5-20251101"
    llm_compare: str = "anthropic:claude-opus-4-5-20251101"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

    # --- storage ---
    data_dir: Path = REPO_ROOT / "data"
    modeling_assumptions_path: Path = BACKEND_DIR / "app" / "assumptions" / "modeling_assumptions.txt"

    # --- free tier / BYOK ---
    free_models: list[str] = Field(default_factory=lambda: ["groq:qwen/qwen3.8-27b", "gemini:gemini-2.5-flash"])
    complex_tasks_require_byok: bool = True
    free_rate_limit_per_hour: int = 20
    byok_rate_limit_per_hour: int = 200
    session_create_limit_per_hour: int = 30
    trust_proxy_headers: bool = False  # honour X-Forwarded-For (only behind a trusted reverse proxy)

    # --- sessions / uploads (ephemeral, nothing outlives the TTL) ---
    session_ttl_minutes: int = 120
    session_sweep_interval_s: int = 300
    max_upload_mb: int = 25
    max_pages: int = 300
    max_docs_per_session: int = 5

    # --- RAG ---
    rag_top_k: int = 5

    # --- LlamaExtract (comparative) ---
    extract_agent_name: str = "comparative-analysis"
    extract_mode: str = "BALANCED"
    compare_timeout_s: int = 300

    # --- analysis / sandbox ---
    sandbox_timeout_s: int = 120
    default_exchange_suffix: str = ".NS"  # appended to bare tickers like "TCS"; indices (^NSEI) and suffixed tickers pass through
    max_period_days: int = 3650  # longest price history an analysis may request
    analysis_default_tickers: list[str] = Field(default_factory=list)

    # --- web ---
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"])

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.sessions_dir.mkdir(parents=True, exist_ok=True)
    s.chroma_dir.mkdir(parents=True, exist_ok=True)
    # Some libraries (LlamaExtract, HF hub, Tavily, provider SDKs) read keys straight from the environment.
    for name in ("google_api_key", "groq_api_key", "anthropic_api_key", "openrouter_api_key",
                 "openai_api_key", "llama_cloud_api_key", "tavily_api_key", "hf_token"):
        value = getattr(s, name)
        if value:
            os.environ.setdefault(name.upper(), value)
    return s
