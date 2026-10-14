import pytest
from langchain_core.documents import Document

from app.services import research, strategy


@pytest.mark.parametrize("text,expected", [
    ("IMPLEMENTATION PLAN:\nplan\nPYTHON CODE:\n```python\nprint(1)\n```", ("plan", "print(1)")),
    ("IMPLEMENTATION PLAN:\nplan\nPYTHON CODE:\n```\nprint(2)\n```", ("plan", "print(2)")),
    ("IMPLEMENTATION PLAN:\nplan\nPYTHON CODE:\nprint(3)", ("plan", "print(3)")),
    ("IMPLEMENTATION PLAN:\nonly plan", ("only plan", "")),
    ("just code", ("", "just code")),
])
def test_parse_response(text, expected):
    assert strategy.parse_response(text) == expected


async def test_pdf_tools(monkeypatch):
    calls = []

    class Retriever:
        async def ainvoke(self, q):
            calls.append(q)
            return [Document(page_content="alpha", metadata={"page": 2}), Document(page_content="beta")]

    got = {}
    monkeypatch.setattr(strategy.documents, "get_retriever", lambda s, i, k: got.update(s=s, i=i, k=k) or Retriever())
    extract, query = strategy.build_pdf_tools("S", "d1", "EXTRACT Q", 4)
    assert got == {"s": "S", "i": "d1", "k": 4}
    out = await extract.async_fn()
    assert out == "[page 2] alpha\n\n[page ?] beta"
    assert await query.async_fn("my question") == out
    assert calls == ["EXTRACT Q", "my question"]


async def test_generate(monkeypatch):
    seen = {}

    class Agent:
        name = description = None

        async def run(self, user_msg):
            seen["msg"] = user_msg
            return "IMPLEMENTATION PLAN:\nP\nPYTHON CODE:\n```python\nC\n```"

    agent = Agent()
    monkeypatch.setattr(strategy.analysis, "build_agent", lambda **kw: seen.update(build=kw) or agent)
    monkeypatch.setattr(strategy.analysis, "response_text", lambda r: r)
    monkeypatch.setattr(strategy, "build_pdf_tools", lambda s, d, q, k: [("tools", s, d, q, k)])
    out = await strategy.generate("S", "d1", "numpy", None, None, 5)
    assert out["plan"] == "P" and out["code"] == "C"
    assert "numpy" in seen["build"]["system_prompt"] and seen["build"]["role"] == "strategy"
    assert seen["build"]["extra_tools"] == [("tools", "S", "d1", strategy.EXTRACT_QUERY, 5)]
    assert agent.name == "TradingStrategyAgent" and seen["msg"].startswith("Read the PDF")
    await strategy.generate("S", "d1", "numpy", "do X", "custom extract", 2)
    assert seen["msg"] == "do X" and seen["build"]["extra_tools"][0][3] == "custom extract"


# ---- research ----
class FakeAgent:
    def __init__(self, **kw):
        self.kw = kw
        self.name = kw["name"]


class FakeWorkflow:
    def __init__(self, agents, root_agent):
        self.agents, self.root_agent = agents, root_agent


async def test_build_workflow_tools_share_request_state(monkeypatch):
    monkeypatch.setattr(research, "FunctionAgent", FakeAgent)
    monkeypatch.setattr(research, "AgentWorkflow", FakeWorkflow)
    monkeypatch.setattr(research, "get_llm", lambda role, fw: ("llm", role))
    searched = {}

    class Tavily:
        def __init__(self, api_key):
            searched["key"] = api_key

        async def search(self, q):
            return {"q": q}

    monkeypatch.setattr(research, "AsyncTavilyClient", Tavily)
    state = {"research_notes": {}, "report_content": "", "review": ""}
    wf = research.build_workflow(state)
    r, w, v = wf.agents
    assert wf.root_agent == "ResearchAgent"
    assert (r.kw["can_handoff_to"], w.kw["can_handoff_to"], v.kw["can_handoff_to"]) == (
        ["WriteAgent"], ["ReviewAgent", "ResearchAgent"], ["WriteAgent"])
    assert r.kw["llm"] == ("llm", "research")
    search_web, record_notes = r.kw["tools"]
    assert "{'q': 'hdfc'}" == await search_web("hdfc") and "key" in searched
    assert "Notes recorded" in await record_notes("n", "title")
    assert "successfully" in await w.kw["tools"][0]("REPORT")
    assert "Review recorded" in await v.kw["tools"][0]("LGTM")
    assert state == {"research_notes": {"title": "n"}, "report_content": "REPORT", "review": "LGTM"}


class AgentOutput:
    def __init__(self, agent, content, tool_names):
        self.current_agent_name = agent
        self.response = type("R", (), {"content": content})()
        self.tool_calls = [type("C", (), {"tool_name": n})() for n in tool_names]


class ToolCallResult:
    def __init__(self, name, output):
        self.tool_name, self.tool_output = name, output


class Agentish:  # has current_agent_name but is neither AgentOutput nor ToolCallResult
    def __init__(self, agent):
        self.current_agent_name = agent


class Handler:
    def __init__(self, events, state):
        self.events, self.state = events, state

    async def stream_events(self):
        for e in self.events:
            yield e

    def __await__(self):
        async def finish():
            self.state["report_content"] = "R"
            self.state["review"] = "V"
        return finish().__await__()


def _patch_stream(monkeypatch, events):
    monkeypatch.setattr(research, "AgentOutput", AgentOutput)
    monkeypatch.setattr(research, "ToolCallResult", ToolCallResult)

    def build(state):
        class WF:
            def run(self, user_msg):
                assert user_msg == "topic"
                return Handler(events, state)
        return WF()

    monkeypatch.setattr(research, "build_workflow", build)


async def test_stream_research_events(monkeypatch):
    events = [Agentish("ResearchAgent"), AgentOutput("ResearchAgent", "x" * 500, ["search_web"]),
              AgentOutput("ResearchAgent", None, []), ToolCallResult("search_web", "y" * 500),
              Agentish("ResearchAgent"), object()]
    _patch_stream(monkeypatch, events)
    out = [e async for e in research.stream_research("topic", preview_chars=10)]
    assert [e["type"] for e in out] == ["agent", "output", "output", "tool_result", "result"]
    assert out[1] == {"type": "output", "agent": "ResearchAgent", "content": "x" * 10, "tools": ["search_web"]}
    assert out[2]["content"] == "" and out[3]["output"] == "y" * 10
    assert out[-1]["report_content"] == "R" and out[-1]["review"] == "V"


async def test_run_research_returns_final_state(monkeypatch):
    _patch_stream(monkeypatch, [Agentish("A")])
    assert await research.run_research("topic") == {"report_content": "R", "review": "V", "research_notes": {}}


async def test_run_research_without_result(monkeypatch):
    async def none(topic):
        return
        yield

    monkeypatch.setattr(research, "stream_research", none)
    with pytest.raises(KeyError):
        await research.run_research("t")
