import json
import time

import pytest

from app.core.config import get_settings
from app.core.llm import current_access
from app.schemas.compare import ComparativeAnalysisOutput, FinalEquityResearchMemoOutput, FinancialModelOutput
from app.services import analysis, compare, documents, rag, research, sessions, strategy
from tests.conftest import BYOK_KEY, PDF


def upload(client, headers, content=PDF, filename="sbi.pdf", **params):
    return client.post("/documents", files={"file": (filename, content, "application/pdf")}, params=params, headers=headers)


@pytest.fixture
def stub_docs(monkeypatch):
    """Session-aware document stubs: ids visible only within the session that uploaded them."""
    reg = {}

    def ingest(sid, filename, content, name=None):
        entry = {"id": "abc123", "name": name or filename, "filename": filename, "path": "p", "collection": "c", "pages": 2}
        reg[(sid, "abc123")] = entry
        return entry

    def get(sid, i):
        return reg[(sid, i)]

    monkeypatch.setattr(documents, "ingest_pdf", ingest)
    monkeypatch.setattr(documents, "list_documents", lambda sid: [v for (s, _), v in reg.items() if s == sid])
    monkeypatch.setattr(documents, "get_document", get)
    return reg


# ---------------- health / catalogs ----------------
def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and set(body["models"]) >= {"rag", "analysis", "research"} and body["free_models"]
    assert set(body["keys_configured"]) == {"anthropic", "openai", "gemini", "groq", "openrouter", "llama_cloud", "tavily"}


def test_models_and_tasks_catalog(client):
    m = client.get("/models").json()
    assert m["free_models"] == get_settings().free_models and m["headers"]["api_key"] == "X-LLM-Api-Key"
    assert list(m["byok_providers"]) == ["anthropic", "openai", "gemini", "groq", "openrouter"]
    assert m["byok_providers"]["openai"]["default"] == "gpt-4o" and m["byok_providers"]["openrouter"]["default"] is None
    assert m["byok_providers"]["anthropic"]["default"] == "claude-sonnet-5-5" and m["complex_tasks_require_byok"]
    t = {x["id"]: x for x in client.get("/tasks").json()}
    assert t["qa"]["free_allowed"] and t["qa"]["max_docs"] == get_settings().max_docs_per_session
    assert not t["strategy"]["free_allowed"] and t["compare_memo"]["min_docs"] == 2 and t["compare_memo"]["max_docs"] == 2


def test_tasks_free_allowed_follows_setting(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "complex_tasks_require_byok", False)
    assert all(x["free_allowed"] for x in client.get("/tasks").json())


# ---------------- sessions ----------------
def test_session_lifecycle(client):
    r = client.post("/sessions")
    assert r.status_code == 201
    sid = r.json()["session_id"]
    assert r.json()["expires_at"] > time.time()
    assert client.get("/documents", headers={"X-Session-Id": sid}).json() == []
    assert client.delete(f"/sessions/{sid}", headers={"X-Session-Id": sid}).status_code == 204
    assert client.get("/documents", headers={"X-Session-Id": sid}).status_code == 401


def test_cannot_delete_someone_elses_session(client):
    a, b = (client.post("/sessions").json()["session_id"] for _ in range(2))
    assert client.delete(f"/sessions/{b}", headers={"X-Session-Id": a}).status_code == 404
    assert client.get("/documents", headers={"X-Session-Id": b}).status_code == 200


def test_session_creation_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "session_create_limit_per_hour", 1)
    assert client.post("/sessions").status_code == 201
    r = client.post("/sessions")
    assert r.status_code == 429 and "Retry-After" in r.headers


@pytest.mark.parametrize("headers", [{}, {"X-Session-Id": "nope"}, {"X-Session-Id": "../../etc/passwd"}])
def test_session_required(client, headers):
    for call in (client.get("/documents", headers=headers), client.post("/chat", json={"question": "q", "document_ids": ["a"]}, headers=headers)):
        assert call.status_code == 401 and call.json()["detail"]["code"] == "invalid_session"


# ---------------- documents ----------------
def test_upload_list_page_delete(client, auth, stub_docs, monkeypatch):
    assert upload(client, auth).json()["id"] == "abc123"
    assert upload(client, auth, filename="a.pdf", name="HDFC").json()["name"] == "HDFC"
    assert [d["id"] for d in client.get("/documents", headers=auth).json()] == ["abc123"]

    monkeypatch.setattr(documents, "get_page", lambda sid, i, p: {"page": p, "content": "c", "metadata": {}})
    assert client.get("/documents/abc123/pages/1", headers=auth).json()["page"] == 1
    for exc, label in ((KeyError("x"), "Document"), (IndexError(9), "Page")):
        def boom(sid, i, p, exc=exc):
            raise exc
        monkeypatch.setattr(documents, "get_page", boom)
        r = client.get("/documents/abc123/pages/99", headers=auth)
        assert r.status_code == 404 and label in r.json()["detail"]

    deleted = []
    monkeypatch.setattr(documents, "delete_document", lambda sid, i: deleted.append((sid, i)))
    assert client.delete("/documents/abc123", headers=auth).status_code == 204 and len(deleted) == 1

    def nodoc(sid, i):
        raise KeyError(i)
    monkeypatch.setattr(documents, "delete_document", nodoc)
    assert client.delete("/documents/abc123", headers=auth).status_code == 404


def test_upload_errors(client, auth, monkeypatch):
    r = upload(client, auth, content=b"<html>", filename="evil.pdf")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_pdf"
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    r = upload(client, auth)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "file_too_large"
    monkeypatch.setattr(get_settings(), "max_upload_mb", 25)

    def reject(*a, **k):
        raise documents.UploadError(409, "too_many_documents", "full")
    monkeypatch.setattr(documents, "ingest_pdf", reject)
    r = upload(client, auth)
    assert r.status_code == 409 and r.json()["detail"] == {"code": "too_many_documents", "message": "full"}


def test_upload_without_filename_is_rejected(client, auth):
    r = client.post("/documents", files={"file": ("", PDF, "application/pdf")}, headers=auth)
    assert r.status_code == 422


def test_documents_are_private_to_their_session(client, stub_docs):
    a, b = ({"X-Session-Id": client.post("/sessions").json()["session_id"]} for _ in range(2))
    upload(client, a)
    assert len(client.get("/documents", headers=a).json()) == 1 and client.get("/documents", headers=b).json() == []
    assert client.get("/documents/abc123/pages/0", headers=b).status_code == 404
    assert client.delete("/documents/abc123", headers=b).status_code == 404


# ---------------- chat ----------------
def test_chat(client, auth, monkeypatch):
    monkeypatch.setattr(rag, "answer", lambda sid, q, ids, k: {"answer": f"{q}|{ids}|{k}", "sources": []})
    r = client.post("/chat", json={"question": "q", "document_ids": ["a"], "top_k": 3}, headers=auth)
    assert r.json()["answer"] == "q|['a']|3"
    assert client.post("/chat", json={"question": "q", "document_ids": []}, headers=auth).status_code == 422

    def nodoc(*a):
        raise KeyError("zzz")
    monkeypatch.setattr(rag, "answer", nodoc)
    r = client.post("/chat", json={"question": "q", "document_ids": ["zzz"]}, headers=auth)
    assert r.status_code == 404 and "zzz" in r.json()["detail"]


# ---------------- free tier vs BYOK gating ----------------
def test_chat_works_on_free_tier_and_byok_reaches_handler(client, auth, byok, monkeypatch):
    seen = []
    monkeypatch.setattr(rag, "answer", lambda *a: seen.append(current_access.get()) or {"answer": "ok", "sources": []})
    body = {"question": "q", "document_ids": ["a"]}
    assert client.post("/chat", json=body, headers=auth).status_code == 200
    assert client.post("/chat", json=body, headers={**auth, **byok}).status_code == 200
    free, paid = seen  # the sync handler (threadpool) sees this request's access
    assert free.tier == "free" and paid.tier == "byok" and paid.api_key == BYOK_KEY and paid.provider == "anthropic"


def test_free_model_allowlist_enforced(client, auth, monkeypatch):
    monkeypatch.setattr(rag, "answer", lambda *a: {"answer": "ok", "sources": []})
    body = {"question": "q", "document_ids": ["a"]}
    ok = {"X-LLM-Provider": "groq", "X-LLM-Model": "qwen/qwen3.8-27b"}
    assert client.post("/chat", json=body, headers={**auth, **ok}).status_code == 200
    bad = client.post("/chat", json=body, headers={**auth, "X-LLM-Provider": "anthropic", "X-LLM-Model": "claude-opus-5-5"})
    assert bad.status_code == 403 and bad.json()["detail"]["code"] == "model_not_free"


def test_complex_endpoints_require_byok(client, auth, stub_docs, byok, monkeypatch):
    async def fake_strategy(sid, doc_id, libs, instr, extract, k):
        return {"plan": "P", "code": f"{doc_id}|{libs}|{k}", "raw": "R"}

    async def fake_research(topic):
        return {"report_content": "R", "review": "ok", "research_notes": {}}

    model = FinancialModelOutput(revenue_projection=1, growth_rate=2, valuation_estimate=3, summary="s")
    memo = FinalEquityResearchMemoOutput(
        company_a_name="A", company_b_name="B", company_a_model=model, company_b_model=model,
        comparative_analysis=ComparativeAnalysisOutput(comparative_analysis="c", overall_recommendation="r"))

    async def fake_compare(sid, a, b):
        return memo

    monkeypatch.setattr(strategy, "generate", fake_strategy)
    monkeypatch.setattr(research, "run_research", fake_research)
    monkeypatch.setattr(compare, "compare", fake_compare)
    upload(client, auth)
    calls = [("/strategy", {"document_id": "abc123", "top_k": 4}), ("/research", {"topic": "HDFC"}),
             ("/research/stream", {"topic": "HDFC"}),
             ("/compare", {"document_id_a": "abc123", "document_id_b": "abc123"})]
    for path, body in calls:
        r = client.post(path, json=body, headers=auth)
        assert r.status_code == 402 and r.json()["detail"]["code"] == "byok_required", path
    assert client.post("/strategy", json=calls[0][1], headers={**auth, **byok}).json()["code"].endswith(
        "pandas, numpy, and statsmodels|4")
    assert client.post("/research", json=calls[1][1], headers={**auth, **byok}).json()["report_content"] == "R"


def test_strategy_and_compare_validation(client, auth, stub_docs, byok, monkeypatch):
    h = {**auth, **byok}
    assert client.post("/strategy", json={"document_id": "nope"}, headers=h).status_code == 404
    upload(client, auth)
    same = client.post("/compare", json={"document_id_a": "abc123", "document_id_b": "abc123"}, headers=h)
    assert same.status_code == 422
    for a, b in (("nope", "abc123"), ("abc123", "nope")):
        assert client.post("/compare", json={"document_id_a": a, "document_id_b": b}, headers=h).status_code == 404

    async def fake_compare(sid, a, b):
        assert (a, b) == ("abc123", "abc123x")
        return FinalEquityResearchMemoOutput.model_validate({
            "company_a_name": "A", "company_b_name": "B",
            "company_a_model": {"revenue_projection": 1, "growth_rate": 2, "valuation_estimate": 3, "summary": "s"},
            "company_b_model": {"revenue_projection": 1, "growth_rate": 2, "valuation_estimate": 3, "summary": "s"},
            "comparative_analysis": {"comparative_analysis": "c", "overall_recommendation": "r"}})

    monkeypatch.setattr(compare, "compare", fake_compare)
    monkeypatch.setitem(stub_docs, (auth["X-Session-Id"], "abc123x"), {"id": "abc123x"})
    r = client.post("/compare", json={"document_id_a": "abc123", "document_id_b": "abc123x"}, headers=h)
    assert r.status_code == 200 and r.json()["company_a_name"] == "A"


def test_research_stream_carries_byok_access(client, byok, monkeypatch):
    async def stream(topic):
        yield {"type": "agent", "agent": "ResearchAgent"}
        yield {"type": "result", "report_content": current_access.get().api_key[:6]}

    monkeypatch.setattr(research, "stream_research", stream)
    r = client.post("/research/stream", json={"topic": "HDFC"}, headers=byok)
    assert r.headers["content-type"].startswith("text/event-stream")
    datas = [json.loads(l[5:]) for l in r.text.splitlines() if l.startswith("data:")]
    assert [d["type"] for d in datas] == ["agent", "result"] and datas[1]["report_content"] == BYOK_KEY[:6]


# ---------------- analysis ----------------
def test_analysis_levels_and_prompts(client, byok, monkeypatch):
    async def fake_run(prompt):
        return f"RESULT[{current_access.get().tier}]"

    monkeypatch.setattr(analysis, "run", fake_run)
    assert client.post("/analysis", json={"task": "technical"}).status_code == 422
    assert client.post("/analysis", json={"task": "compare", "ticker": "A.NS"}).status_code == 422
    assert client.post("/analysis", json={"task": "custom"}).status_code == 422
    r = client.post("/analysis", json={"task": "technical", "ticker": "TCS", "short_window": 5, "long_window": 20,
                                       "period": "3mo"}).json()
    assert r["result"] == "RESULT[free]" and "TCS.NS" in r["prompt"] and "5-day" in r["prompt"]
    assert "last 3 months" in r["prompt"] and "start='" in r["prompt"]
    r = client.post("/analysis", json={"task": "compare", "tickers": ["A.NS", "B.NS"]}, headers=byok).json()
    assert "A.NS, B.NS" in r["prompt"] and r["result"] == "RESULT[byok]"
    custom = {"task": "custom", "prompt": "Do a thing"}
    blocked = client.post("/analysis", json=custom)
    assert blocked.status_code == 402 and blocked.json()["detail"]["code"] == "byok_required"
    assert client.post("/analysis", json=custom, headers=byok).json()["prompt"] == "Do a thing"


def test_analysis_period_validation_costs_no_rate_limit(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "free_rate_limit_per_hour", 1)
    for body in ({"task": "price_summary", "ticker": "TCS", "period": "soon"},
                 {"task": "price_summary", "ticker": "TCS", "period": "99y"},
                 {"task": "technical", "ticker": "TCS", "period": "1mo", "long_window": 200}):
        r = client.post("/analysis", json=body)
        assert r.status_code == 422, body
    assert "Invalid period" in client.post("/analysis", json={"task": "compare", "tickers": ["A", "B"], "period": "x"}).json()["detail"]


def test_free_tier_rate_limit(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "free_rate_limit_per_hour", 2)

    async def fake_run(prompt):
        return "ok"

    monkeypatch.setattr(analysis, "run", fake_run)
    body = {"task": "price_summary", "ticker": "TCS.NS"}
    assert [client.post("/analysis", json=body).status_code for _ in range(2)] == [200, 200]
    r = client.post("/analysis", json=body)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0 and r.json()["detail"]["code"] == "rate_limited"


def test_invalid_byok_headers_rejected(client):
    r = client.post("/analysis", json={"task": "price_summary", "ticker": "TCS.NS"},
                    headers={"X-LLM-Api-Key": "k" * 20, "X-LLM-Provider": "nope"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_provider"


# ---------------- /models/validate ----------------
def test_validate_key(client, byok, monkeypatch):
    from app.api import models as models_api

    class LLM:
        async def acomplete(self, prompt):
            return "OK"

    monkeypatch.setattr(models_api, "get_llm", lambda role, fw: LLM())
    assert client.post("/models/validate", headers=byok).json() == {"ok": True}
    r = client.post("/models/validate")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "byok_required"

    class Bad:
        async def acomplete(self, prompt):
            raise RuntimeError(f"401 invalid x-api-key {BYOK_KEY}")

    monkeypatch.setattr(models_api, "get_llm", lambda role, fw: Bad())
    r = client.post("/models/validate", headers=byok)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "key_rejected"
    assert BYOK_KEY not in r.text and "[redacted]" in r.text


# ---------------- error handling ----------------
def test_unhandled_errors_become_502_without_leaking_keys(client, auth, byok, monkeypatch):
    def boom(*a):
        raise RuntimeError(f"auth failed for {BYOK_KEY} and gsk_abcdefghijklmnop")

    monkeypatch.setattr(rag, "answer", boom)
    r = client.post("/chat", json={"question": "q", "document_ids": ["a"]}, headers={**auth, **byok})
    assert r.status_code == 502 and "RuntimeError: auth failed" in r.json()["detail"]
    assert BYOK_KEY not in r.text and "gsk_abcdefghijklmnop" not in r.text


def test_network_failures_get_a_friendly_502(client, auth, monkeypatch):
    import httpx

    def dns_down(*a):
        raise httpx.ConnectError("[Errno 8] nodename nor servname provided, or not known")

    def wrapped(*a):
        try:
            dns_down()
        except httpx.ConnectError as e:
            raise RuntimeError("provider call failed") from e

    for fn in (dns_down, wrapped):
        monkeypatch.setattr(rag, "answer", fn)
        r = client.post("/chat", json={"question": "q", "document_ids": ["a"]}, headers=auth)
        assert r.status_code == 502 and "Network error reaching an upstream service" in r.json()["detail"]


# ---------------- lifespan sweeper ----------------
def test_background_sweeper_runs_and_stops(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    calls = []
    monkeypatch.setattr(sessions, "sweep_expired", lambda: calls.append(1) or 0)
    monkeypatch.setattr(get_settings(), "session_sweep_interval_s", 0.01)
    with TestClient(app):
        deadline = time.time() + 3
        while len(calls) < 2 and time.time() < deadline:
            time.sleep(0.01)
    assert len(calls) >= 2


def test_502_responses_carry_cors_headers(client, auth, monkeypatch):
    def boom(*a):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(rag, "answer", boom)
    r = client.post("/chat", json={"question": "q", "document_ids": ["a"]},
                    headers={**auth, "Origin": "http://localhost:3000"})
    assert r.status_code == 502 and r.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_error_middleware_passthrough_and_midstream_failures():
    from app.main import UpstreamErrorMiddleware

    sent = []

    async def send(message):
        sent.append(message["type"])

    async def lifespan_app(scope, receive, send):
        await send({"type": "lifespan.startup.complete"})

    await UpstreamErrorMiddleware(lifespan_app)({"type": "lifespan"}, None, send)  # non-http scopes pass through
    assert sent == ["lifespan.startup.complete"]

    async def streaming_then_crash(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("died mid-stream")

    with pytest.raises(RuntimeError, match="mid-stream"):
        await UpstreamErrorMiddleware(streaming_then_crash)({"type": "http"}, None, send)
