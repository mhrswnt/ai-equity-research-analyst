# AI Equity Research Assistant

FastAPI backend (frontend later) built from the experiments in `notebooks/`.

| Endpoint | Capability | Stack | Notebook |
|---|---|---|---|
| `POST/GET/DELETE /documents`, `GET /documents/{id}/pages/{n}` | PDF ingest/list/inspect | LangChain + Chroma | ai_equity_research_analyst |
| `POST /chat` | Q&A and cross-company comparison over PDFs | LangChain agent | ai_equity_research_analyst |
| `POST /analysis` | price summary, technicals, correlation, backtest, custom | LlamaIndex agent + sandboxed Python | stock_price_analysis_with_ai |
| `POST /strategy` | PDF strategy -> plan + code | LlamaIndex agent + shared Chroma retriever | pdf_to_code_with_llamaindex |
| `POST /research`, `/research/stream` (SSE) | Research -> Write -> Review web report | LlamaIndex AgentWorkflow + Tavily | automated_equity_research |
| `POST /compare` | Two-company memo | LlamaExtract + LlamaIndex Workflow | comparative_analysis_workflows |

## Access model: free tier + BYOK
- **Session**: `POST /sessions` -> `session_id`; send it as `X-Session-Id`. Documents/vectors are private to the session and deleted on `DELETE /sessions/{id}` or after `SESSION_TTL_MINUTES` idle. Nothing else is persisted.
- **Free tier** (no key headers): operator keys, allowlisted `FREE_MODELS` only, basic tasks (`/chat`, `/analysis` presets), per-IP rate limit. Complex tasks (`/strategy`, `/research`, `/compare`, custom analysis) return `402 byok_required`.
- **BYOK**: send `X-LLM-Provider` (anthropic|openai|gemini|groq|openrouter), `X-LLM-Api-Key`, optional `X-LLM-Model` on each request. The key is held only for that request (never stored, logged, or put in `os.environ`; error text is redacted). Check a key with `POST /models/validate`.
- `GET /models` and `GET /tasks` describe providers, free models, task levels and document requirements for the UI. Serve over HTTPS in production.

## Frontend (Next.js, `frontend/`)
Screens follow the design references and call only the backend API: Overview, Document Q&A (library, citations, source panel), Compare, Correlation, Technical, Backtest, Strategy lab, Web research (live SSE feed). The model-access dialog implements free vs BYOK; the key lives in `sessionStorage` only.
```
cd frontend && npm install && npm run dev        # http://localhost:3000, needs the backend on :8000
npm test && npm run typecheck && npm run build
```
Set `NEXT_PUBLIC_API_URL` (see `frontend/.env.example`) if the backend is elsewhere; add the frontend origin to `CORS_ORIGINS` in `.env`.

## Run (conda env `my-quant-stack`)
```
cp .env.example .env        # fill keys; .env is gitignored
cd backend
conda run -n my-quant-stack env PYTHONPATH=. uvicorn app.main:app --reload   # docs at /docs
```
Models are picked per role in `.env` (`LLM_RAG=gemini:gemini-2.5-flash`, ...); any request can override with `"model": "<provider>:<model>"`.
Tests: `cd backend && python -m pytest` (needs `requirements-dev.txt`; enforces 100% line+branch coverage)
