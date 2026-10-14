"""PDF trading strategy -> implementation plan + Python code.
Reuses the shared Chroma retriever for the PDF tools and the shared LlamaIndex agent builder."""
from llama_index.core.tools import FunctionTool

from app.services import analysis, documents

SYSTEM_PROMPT = """You are a trading strategy implementation specialist. Your task is to:

1. First, use extract_strategy to get the trading strategy from the PDF
2. Then, use query_pdf if you need additional details about specific aspects
3. Finally, create a complete implementation plan AND Python code

When you have gathered enough information, provide your response in this exact format:

IMPLEMENTATION PLAN:
[Your detailed plan here]

PYTHON CODE:
```python
[Your complete, executable Python code here]
```

The Python code should be complete and runnable, including all imports, functions, 
and a main execution block. Focus on the core strategy logic - use {libraries} for the implementation.
"""

EXTRACT_QUERY = (
    "Extract a detailed description of the pairs trading strategy from this document. "
    "Include: 1) The assets being traded, 2) The statistical methods used, "
    "3) The entry and exit signals, 4) Any risk management rules."
)


def _join(docs) -> str:
    return "\n\n".join(f"[page {d.metadata.get('page', '?')}] {d.page_content}" for d in docs)


def build_pdf_tools(sid: str, doc_id: str, extract_query: str, k: int):
    retriever = documents.get_retriever(sid, doc_id, k)

    async def query_pdf(question: str) -> str:
        """Query the strategy PDF for specific information."""
        return _join(await retriever.ainvoke(question))

    async def extract_strategy() -> str:
        """Extract the complete trading strategy description from the PDF."""
        return _join(await retriever.ainvoke(extract_query))

    return [FunctionTool.from_defaults(async_fn=extract_strategy), FunctionTool.from_defaults(async_fn=query_pdf)]


def parse_response(text: str) -> tuple[str, str]:
    """Split on the literal markers; fall back to treating everything as code (as in the notebook)."""
    if "IMPLEMENTATION PLAN:" not in text:
        return "", text
    parts = text.split("PYTHON CODE:")
    plan = parts[0].replace("IMPLEMENTATION PLAN:", "").strip()
    code = ""
    if len(parts) > 1:
        code = parts[1].strip()
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()
    return plan, code


async def generate(sid: str, doc_id: str, libraries: str, instruction: str | None, extract_query: str | None,
                   top_k: int) -> dict:
    agent = analysis.build_agent(
        role="strategy", system_prompt=SYSTEM_PROMPT.format(libraries=libraries),
        extra_tools=build_pdf_tools(sid, doc_id, extract_query or EXTRACT_QUERY, top_k),
    )
    agent.name = "TradingStrategyAgent"
    agent.description = "Converts trading strategy PDFs into Python code."
    instruction = instruction or (
        "Read the PDF and convert the trading strategy into Python code. "
        "First extract the strategy, then create an implementation plan and generate "
        "complete, executable Python code."
    )
    text = analysis.response_text(await agent.run(user_msg=instruction))
    plan, code = parse_response(text)
    return {"plan": plan, "code": code, "raw": text}
