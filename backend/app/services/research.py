"""Research -> Write -> Review multi-agent workflow (LlamaIndex AgentWorkflow + Tavily). State is request-scoped."""
from typing import AsyncIterator

from llama_index.core.agent.workflow import AgentOutput, AgentWorkflow, FunctionAgent, ToolCallResult
from tavily import AsyncTavilyClient

from app.core.config import get_settings
from app.core.llm import get_llm


def build_workflow(state: dict) -> AgentWorkflow:
    llm = get_llm("research", "llamaindex")
    api_key = get_settings().tavily_api_key

    async def search_web(query: str) -> str:
        """Search the web for information on a topic."""
        return str(await AsyncTavilyClient(api_key=api_key).search(query))

    async def record_notes(notes: str, notes_title: str) -> str:
        """Record research notes with a title."""
        state["research_notes"][notes_title] = notes
        return f"Notes recorded under title: {notes_title}"

    async def write_report(report_content: str) -> str:
        """Write the final report content."""
        state["report_content"] = report_content
        return "Report written successfully."

    async def review_report(review: str) -> str:
        """Review the report and provide feedback."""
        state["review"] = review
        return f"Review recorded: {review}"

    research_agent = FunctionAgent(
        name="ResearchAgent",
        description="Searches the web for information and records notes.",
        system_prompt=(
            "You are the ResearchAgent. Search the web for information on the given topic "
            "and record your findings as notes using the record_notes tool. "
            "Once you have gathered enough information (at least 2-3 searches), "
            "hand off to the WriteAgent to write the report."
        ),
        llm=llm, tools=[search_web, record_notes], can_handoff_to=["WriteAgent"],
    )
    write_agent = FunctionAgent(
        name="WriteAgent",
        description="Writes reports based on research notes.",
        system_prompt=(
            "You are the WriteAgent. Write a concise report in markdown format based on "
            "what the ResearchAgent found. Use the write_report tool to save the report. "
            "Once written, hand off to the ReviewAgent for feedback."
        ),
        llm=llm, tools=[write_report], can_handoff_to=["ReviewAgent", "ResearchAgent"],
    )
    review_agent = FunctionAgent(
        name="ReviewAgent",
        description="Reviews reports and provides feedback.",
        system_prompt=(
            "You are the ReviewAgent. Review the report and use the review_report tool "
            "to record your feedback. Approve the report if it's good, or request specific "
            "changes. If major changes are needed, hand off to the WriteAgent."
        ),
        llm=llm, tools=[review_report], can_handoff_to=["WriteAgent"],
    )
    return AgentWorkflow(agents=[research_agent, write_agent, review_agent], root_agent=research_agent.name)


async def stream_research(topic: str, preview_chars: int = 200) -> AsyncIterator[dict]:
    """Yield progress events (agent switch / output / tool call / tool result), then a final 'result' event."""
    state = {"research_notes": {}, "report_content": "", "review": ""}
    handler = build_workflow(state).run(user_msg=topic)
    current_agent = None
    async for event in handler.stream_events():
        if hasattr(event, "current_agent_name") and event.current_agent_name != current_agent:
            current_agent = event.current_agent_name
            yield {"type": "agent", "agent": current_agent}
        elif isinstance(event, AgentOutput):
            yield {"type": "output", "agent": current_agent,
                   "content": (event.response.content or "")[:preview_chars],
                   "tools": [c.tool_name for c in event.tool_calls]}
        elif isinstance(event, ToolCallResult):
            yield {"type": "tool_result", "tool": event.tool_name, "output": str(event.tool_output)[:preview_chars]}
    await handler
    yield {"type": "result", **state}


async def run_research(topic: str) -> dict:
    result = {}
    async for ev in stream_research(topic):
        if ev["type"] == "result":
            result = ev
    return {k: result[k] for k in ("report_content", "review", "research_notes")}
