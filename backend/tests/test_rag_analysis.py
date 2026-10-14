from datetime import date, timedelta

import pytest
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from app.core.config import get_settings
from app.services import analysis, rag, sandbox


class FakeRetriever(BaseRetriever):
    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun):
        return [Document(page_content="hit")]


def test_flatten_content():
    assert rag.flatten_content("text") == "text"
    assert rag.flatten_content([{"text": "a"}, {"text": "b"}, "c", {"type": "x"}]) == "abc"


def test_build_tools_names_and_k(monkeypatch):
    docs = {"d1": {"name": "HDFC Bank!"}, "d2": {"name": "SBI"}}
    seen = []
    monkeypatch.setattr(rag.documents, "get_document", lambda sid, i: docs[i])
    monkeypatch.setattr(rag.documents, "get_retriever", lambda sid, i, k: seen.append((sid, i, k)) or FakeRetriever())
    tools = rag.build_tools("S", ["d1", "d2"], k=7)
    assert [t.name for t in tools] == ["hdfc_bank_search_d1", "sbi_search_d2"]
    assert "HDFC Bank!" in tools[0].description and seen == [("S", "d1", 7), ("S", "d2", 7)]
    assert tools[0].metadata == {"document_id": "d1", "document": "HDFC Bank!"}
    content, artifact = tools[0].func("q")  # content_and_artifact: text for the LLM + Documents for citations
    assert content == "hit" and artifact[0].page_content == "hit"


class Msg:
    def __init__(self, type, content, name=None, artifact=None):
        self.type, self.content, self.name, self.artifact = type, content, name, artifact


def test_answer(monkeypatch):
    captured = {}

    class Agent:
        def invoke(self, payload):
            captured["payload"] = payload
            chunks = [Document(page_content="evidence " * 300, metadata={"page": 2}), Document(page_content="b")]
            return {"messages": [Msg("human", "q"), Msg("tool", "evidence", "sbi_search", chunks),
                                 Msg("tool", "none", "sbi_search", None),
                                 Msg("ai", [{"text": "line1\\nline2"}])]}

    tool = type("T", (), {"name": "sbi_search", "metadata": {"document_id": "d1", "document": "SBI"}})()
    monkeypatch.setattr(rag, "build_tools", lambda sid, ids, k: captured.update(args=(sid, ids, k)) or [tool])
    monkeypatch.setattr(rag, "get_llm", lambda role, fw: ("llm", role, fw))
    monkeypatch.setattr(rag, "create_agent", lambda llm, tools: captured.update(llm=llm, tools=tools) or Agent())
    out = rag.answer("S", "what?", ["d1"], k=3)
    assert out["answer"] == "line1\nline2"
    assert out["sources"] == [
        {"tool": "sbi_search", "document_id": "d1", "document": "SBI", "page": 2, "page_number": 3,
         "excerpt": ("evidence " * 300)[:rag.EXCERPT_CHARS]},
        {"tool": "sbi_search", "document_id": "d1", "document": "SBI", "page": None, "page_number": None,
         "excerpt": "b"}]
    assert captured["llm"] == ("llm", "rag", "langchain") and captured["args"] == ("S", ["d1"], 3)
    assert captured["payload"] == {"messages": [("user", "what?")]}


def test_answer_requires_documents():
    with pytest.raises(ValueError):
        rag.answer("S", "q", [])


# ---------------- sandbox / analysis ----------------
async def test_sandbox_runs_and_scrubs_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY_X", "leak")
    r = await sandbox.run_python("import os;print(os.environ.get('SECRET_KEY_X'));print('hi')")
    assert r == {"returncode": 0, "stdout": "None\nhi\n", "stderr": ""}


async def test_sandbox_error_and_timeout(monkeypatch):
    assert (await sandbox.run_python("raise SystemExit(3)"))["returncode"] == 3
    r = await sandbox.run_python("import time;time.sleep(5)", timeout_s=1)
    assert r["returncode"] == -1 and "Timed out after 1s" in r["stderr"]
    monkeypatch.setattr(get_settings(), "sandbox_timeout_s", 1)  # default timeout comes from settings
    assert "Timed out after 1s" in (await sandbox.run_python("import time;time.sleep(5)"))["stderr"]


async def test_sandbox_caps_output(monkeypatch):
    monkeypatch.setattr(sandbox, "MAX_OUTPUT_CHARS", 10)
    assert len((await sandbox.run_python("print('x'*100)"))["stdout"]) == 10


TODAY = date(2026, 10, 3)


@pytest.mark.parametrize("period,start,label", [
    ("3mo", date(2026, 7, 3), "last 3 months"),
    ("6M", date(2026, 4, 3), "last 6 months"),
    ("1y", date(2025, 10, 3), "last 1 year"),
    ("3Y", date(2023, 10, 3), "last 3 years"),
    ("1000d", date(2024, 1, 7), "last 1000 days"),
    ("12w", date(2026, 7, 11), "last 12 weeks"),
    ("2wk", date(2026, 9, 19), "last 2 weeks"),
    (" 5 m ", date(2026, 5, 3), "last 5 months"),
    ("ytd", date(2026, 1, 1), "year to date"),
])
def test_resolve_period_is_calendar_based_with_exclusive_end(period, start, label):
    p = analysis.resolve_period(period, TODAY)
    assert (p.start, p.end, p.label) == (start, date(2026, 10, 4), label)
    assert p.days == (date(2026, 10, 4) - start).days


@pytest.mark.parametrize("bad", ["", "abc", "3", "mo3", "-5d", "0d", "1.5y", "3 parsecs"])
def test_resolve_period_rejects_garbage(bad):
    with pytest.raises(ValueError):
        analysis.resolve_period(bad, TODAY)


def test_resolve_period_defaults_to_today():
    assert analysis.resolve_period("1d").end == date.today() + timedelta(days=1)


def test_normalize_ticker(monkeypatch):
    assert analysis.normalize_ticker(" tcs ") == "TCS.NS"
    assert analysis.normalize_ticker("RELIANCE.BO") == "RELIANCE.BO" and analysis.normalize_ticker("^nsei") == "^NSEI"
    assert analysis.normalize_ticker("  ") == ""
    monkeypatch.setattr(get_settings(), "default_exchange_suffix", ".BO")
    assert analysis.normalize_ticker("tcs") == "TCS.BO"


def test_min_calendar_days():
    assert analysis.min_calendar_days(50) == 77 and analysis.min_calendar_days(20) == 35


def test_build_prompt_presets_use_explicit_dates():
    base = dict(ticker="tcs", period="3mo", short_window=10, long_window=30, rsi_period=7, sma_window=15)
    for task in ("price_summary", "technical", "backtest"):
        prompt = analysis.build_prompt(task, base, TODAY)
        assert "TCS.NS" in prompt and "start='2026-07-03'" in prompt and "end='2026-10-04'" in prompt
        assert "last 3 months" in prompt and "do NOT use the period argument" in prompt
    t = analysis.build_prompt("technical", base, TODAY)
    assert "10-day" in t and "30-day" in t and "7-day" in t
    assert "15-day SMA" in analysis.build_prompt("backtest", base, TODAY)
    c = analysis.build_prompt("compare", dict(tickers=["a", "b.BO"], period="1000d"), TODAY)
    assert "A.NS, B.BO" in c and "['A.NS', 'B.BO']" in c and "start='2024-01-07'" in c


def test_build_prompt_default_periods_and_ignored_none():
    prompt = analysis.build_prompt("price_summary", dict(ticker="X", period=None), TODAY)
    assert "last 1 month" in prompt and "start='2026-09-03'" in prompt
    assert "last 6 months" in analysis.build_prompt("technical", dict(ticker="X", short_window=5, long_window=20, rsi_period=14), TODAY)


def test_build_prompt_validation(monkeypatch):
    with pytest.raises(ValueError, match="Unknown task"):
        analysis.build_prompt("nope", {})
    with pytest.raises(ValueError, match="Period too long"):
        analysis.build_prompt("price_summary", dict(ticker="X", period="11y"), TODAY)
    with pytest.raises(ValueError, match="needs at least 77 calendar days"):
        analysis.build_prompt("technical", dict(ticker="X", period="1mo", short_window=20, long_window=50, rsi_period=14), TODAY)
    with pytest.raises(ValueError, match="needs at least"):
        analysis.build_prompt("backtest", dict(ticker="X", period="2w", sma_window=100), TODAY)
    monkeypatch.setattr(get_settings(), "max_period_days", 20000)
    assert analysis.build_prompt("price_summary", dict(ticker="X", period="11y"), TODAY)


async def test_code_interpreter_formats_result(monkeypatch):
    async def fake(code):
        return {"returncode": 0, "stdout": "OUT", "stderr": "ERR"}

    monkeypatch.setattr(analysis.sandbox, "run_python", fake)
    assert await analysis.code_interpreter("print(1)") == "returncode=0\nSTDOUT:\nOUT\nSTDERR:\nERR"


def test_build_agent_wires_tools_and_llm(monkeypatch):
    class FakeAgent:
        def __init__(self, **kw):
            self.kw = kw

    monkeypatch.setattr(analysis, "FunctionAgent", FakeAgent)
    monkeypatch.setattr(analysis, "get_llm", lambda role, fw: (role, fw))
    a = analysis.build_agent(role="strategy", system_prompt="sp", extra_tools=["extra"])
    assert a.kw["llm"] == ("strategy", "llamaindex") and a.kw["system_prompt"] == "sp"
    assert a.kw["tools"][0].metadata.name == "code_interpreter" and a.kw["tools"][1] == "extra"
    assert analysis.build_agent().kw["system_prompt"] == analysis.SYSTEM_PROMPT


class Block:
    def __init__(self, text):
        self.text = text


class Result:
    def __init__(self, blocks):
        self.response = type("R", (), {"blocks": blocks})()

    def __str__(self):
        return "fallback\\ntext"


def test_response_text():
    assert analysis.response_text(Result([Block("a\\nb"), object(), Block("c")])) == "a\nbc"
    assert analysis.response_text(Result([])) == "fallback\ntext"
    assert analysis.response_text("plain") == "plain"


async def test_run(monkeypatch):
    class Agent:
        async def run(self, user_msg):
            return Result([Block(f"done: {user_msg}")])

    monkeypatch.setattr(analysis, "build_agent", lambda: Agent())
    assert await analysis.run("go") == "done: go"


def test_answer_unknown_tool_has_no_origin(monkeypatch):
    class Agent:
        def invoke(self, payload):
            return {"messages": [Msg("tool", "x", "mystery", [Document(page_content="c", metadata={"page": 0})]),
                                 Msg("ai", "done")]}

    monkeypatch.setattr(rag, "build_tools", lambda sid, ids, k: [])
    monkeypatch.setattr(rag, "get_llm", lambda role, fw: None)
    monkeypatch.setattr(rag, "create_agent", lambda llm, tools: Agent())
    out = rag.answer("S", "q", ["d1"])
    assert out["sources"] == [{"tool": "mystery", "page": 0, "page_number": 1, "excerpt": "c"}]
