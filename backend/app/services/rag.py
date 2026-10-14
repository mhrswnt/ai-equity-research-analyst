"""LangChain RAG agent: one retriever tool per selected document, one agent (Q&A + cross-company comparison)."""
import re

from langchain.agents import create_agent
from langchain_core.tools import create_retriever_tool

from app.core.llm import get_llm
from app.services import documents


EXCERPT_CHARS = 1200


def _tool_name(doc: dict) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", doc["name"]).strip("_").lower()[:40] + "_search"


def build_tools(sid: str, doc_ids: list[str], k: int | None = None):
    tools = []
    for doc_id in doc_ids:
        doc = documents.get_document(sid, doc_id)
        tool = create_retriever_tool(
            documents.get_retriever(sid, doc_id, k),
            f"{_tool_name(doc)}_{doc_id[:4]}",
            f"Search for information about {doc['name']} financial statements. "
            f"Use this for any questions about {doc['name']} revenue, income, expenses, or other financial metrics.",
            response_format="content_and_artifact",  # keeps the retrieved Documents (page metadata) for citations
        )
        tool.metadata = {"document_id": doc_id, "document": doc["name"]}
        tools.append(tool)
    return tools


def flatten_content(content) -> str:
    """Gemini returns a list of blocks; other providers return a plain string."""
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)


def answer(sid: str, question: str, doc_ids: list[str], k: int | None = None) -> dict:
    if not doc_ids:
        raise ValueError("At least one document id is required.")
    tools = build_tools(sid, doc_ids, k)
    agent = create_agent(get_llm("rag", "langchain"), tools)
    result = agent.invoke({"messages": [("user", question)]})
    origin = {t.name: t.metadata for t in tools}
    sources = []  # one entry per retrieved chunk, in retrieval order, so the UI can number citations
    for m in result["messages"]:
        if getattr(m, "type", "") == "tool":
            for chunk in getattr(m, "artifact", None) or []:
                page = chunk.metadata.get("page")
                sources.append({
                    "tool": m.name, **origin.get(m.name, {}), "page": page,
                    "page_number": page + 1 if isinstance(page, int) else None,
                    "excerpt": chunk.page_content[:EXCERPT_CHARS],
                })
    return {"answer": flatten_content(result["messages"][-1].content).replace("\\n", "\n"), "sources": sources}
