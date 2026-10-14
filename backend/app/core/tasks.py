"""Task catalog: single source of truth for which tasks exist, their tier level and document needs.
Routers read `level_of(...)`; GET /tasks serves the same data to the UI."""
from dataclasses import dataclass
from typing import Literal

Level = Literal["basic", "complex"]


@dataclass(frozen=True)
class Task:
    id: str
    label: str
    endpoint: str
    level: Level
    min_docs: int
    max_docs: int | None  # None = up to the per-session document cap
    description: str


TASKS: tuple[Task, ...] = (
    Task("qa", "Ask questions about documents", "/chat", "basic", 1, None,
         "RAG Q&A over one or more uploaded PDFs, including cross-company comparison questions."),
    Task("analysis_price_summary", "Price summary", "/analysis", "basic", 0, 0,
         "% change, high/low close and average volume for an NSE ticker."),
    Task("analysis_technical", "Technical analysis", "/analysis", "basic", 0, 0,
         "SMA crossover and RSI signals for an NSE ticker."),
    Task("analysis_compare", "Compare stocks", "/analysis", "basic", 0, 0,
         "Normalized returns and correlation matrix across tickers."),
    Task("analysis_backtest", "SMA backtest", "/analysis", "basic", 0, 0,
         "SMA strategy backtest vs buy-and-hold."),
    Task("analysis_custom", "Custom analysis", "/analysis", "complex", 0, 0,
         "Free-form instruction executed by the coding agent."),
    Task("strategy", "Strategy to code", "/strategy", "complex", 1, 1,
         "Turn a strategy PDF into an implementation plan and Python code."),
    Task("research", "Web research report", "/research", "complex", 0, 0,
         "Research -> write -> review agents produce a report on a topic."),
    Task("compare_memo", "Two-company memo", "/compare", "complex", 2, 2,
         "Structured financial models and investment memo comparing two company PDFs."),
)

_BY_ID = {t.id: t for t in TASKS}


def level_of(task_id: str) -> Level:
    return _BY_ID[task_id].level


def analysis_level(analysis_task: str) -> Level:
    """/analysis request task ('technical', 'custom', ...) -> catalog level."""
    return level_of(f"analysis_{analysis_task}")
