"""LlamaIndex FunctionAgent that writes + executes Python (yfinance) for stock analysis.
Single coding agent: also used by the strategy service."""
import math
import re
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.tools import FunctionTool

from app.core.config import get_settings
from app.core.llm import get_llm
from app.services import sandbox

SYSTEM_PROMPT = (
    "You are a Python code expert for financial analysis. "
    "Always use the code_interpreter tool to write and execute Python code "
    "when analyzing data. Use yfinance to fetch indian stock data."
)

# Prompt templates ported from stock_price_analysis_with_ai.ipynb. Dates are resolved server-side and passed as explicit
# start/end: yfinance's `period="90d"` means ~90 *trading* days (about 4 calendar months), which made "3M" and "6M"
# windows come out wrong when the agent picked period strings itself.
FETCH_ONE = (
    "Fetch daily prices with yfinance using explicit dates, e.g. "
    "yf.Ticker('{ticker}').history(start='{start}', end='{end}', interval='1d', auto_adjust=True) "
    "(end is exclusive; do NOT use the period argument). Report how many rows came back and the first/last date; "
    "if there is no data, say the ticker may be wrong or delisted."
)
FETCH_MANY = (
    "Fetch daily closing prices for all tickers with yfinance using explicit dates, e.g. "
    "yf.download({tickers_list}, start='{start}', end='{end}', interval='1d', auto_adjust=True)['Close'] "
    "(end is exclusive; do NOT use the period argument). Report the row count and first/last date, "
    "and flag any ticker that returned no data."
)
PRESETS = {
    "price_summary": (
        "Use the code interpreter to analyze {ticker} stock over {span} ({start} to {end}):\n"
        "1. " + FETCH_ONE + "\n"
        "2. Calculate the percentage change from start to end\n"
        "3. Find the highest and lowest closing prices\n"
        "4. Calculate the average daily trading volume\n"
        "5. Print a summary of the analysis"
    ),
    "technical": (
        "Use the code interpreter to perform technical analysis on {ticker} over {span} ({start} to {end}):\n"
        "1. " + FETCH_ONE + "\n"
        "2. Calculate the {short_window}-day and {long_window}-day SMA\n"
        "3. Determine if there's a bullish or bearish crossover\n"
        "4. Calculate the RSI (Relative Strength Index) using a {rsi_period}-day period\n"
        "5. print a technical analysis summary with buy/sell signals"
    ),
    "compare": (
        "Use the code interpreter to compare {tickers} over {span} ({start} to {end}):\n"
        "1. " + FETCH_MANY + "\n"
        "2. Normalize prices to percentage returns from the start date\n"
        "3. Calculate the correlation matrix between the stocks\n"
        "4. Identify which pair has the highest correlation\n"
        "5. Print the results"
    ),
    "backtest": (
        "Use the code interpreter to backtest a simple strategy on {ticker} over {span} ({start} to {end}):\n"
        "1. " + FETCH_ONE + "\n"
        "2. Generate buy signals when price crosses above the {sma_window}-day SMA\n"
        "3. Generate sell signals when price crosses below the {sma_window}-day SMA\n"
        "4. Calculate the return if you followed these signals\n"
        "5. Compare to buy-and-hold return over the same period"
    ),
}
DEFAULT_PERIOD = {"price_summary": "1mo", "technical": "6mo", "compare": "6mo", "backtest": "6mo"}

_PERIOD_RE = re.compile(r"^\s*(\d+)\s*(d|w|wk|mo|m|y)\s*$", re.IGNORECASE)
_UNIT_NAMES = {"d": "day", "w": "week", "wk": "week", "mo": "month", "m": "month", "y": "year"}


class Period:
    """A resolved price-history window."""

    def __init__(self, start: date, end: date, label: str):
        self.start, self.end, self.label = start, end, label

    @property
    def days(self) -> int:
        return (self.end - self.start).days


def resolve_period(period: str, today: date | None = None) -> Period:
    """'3mo', '6M', '1y', '3Y', '1000d', '12w' (calendar based) or 'ytd' -> explicit [start, end) dates.
    `end` is tomorrow because yfinance's end date is exclusive."""
    today = today or date.today()
    end = today + timedelta(days=1)
    text = period.strip().lower()
    if text == "ytd":
        return Period(date(today.year, 1, 1), end, "year to date")
    m = _PERIOD_RE.match(text)
    if not m:
        raise ValueError(f"Invalid period '{period}'. Use e.g. 30d, 3mo, 6mo, 1y, 3y, 1000d or ytd.")
    n, unit = int(m.group(1)), m.group(2).lower()
    if n < 1:
        raise ValueError("Period must be at least 1.")
    start = {"d": lambda: today - timedelta(days=n), "w": lambda: today - timedelta(weeks=n),
             "wk": lambda: today - timedelta(weeks=n), "mo": lambda: today - relativedelta(months=n),
             "m": lambda: today - relativedelta(months=n), "y": lambda: today - relativedelta(years=n)}[unit]()
    name = _UNIT_NAMES[unit]
    return Period(start, end, f"last {n} {name}{'s' if n != 1 else ''}")


def min_calendar_days(window: int) -> int:
    """Calendar days needed to see `window` trading days (5/7 trading ratio plus holiday slack)."""
    return math.ceil(window * 7 / 5) + 7


def normalize_ticker(raw: str) -> str:
    t = raw.strip().upper()
    if not t or "." in t or t.startswith("^"):
        return t
    return t + get_settings().default_exchange_suffix


def build_prompt(task: str, params: dict, today: date | None = None) -> str:
    """Fill a preset. `params` may carry `period` ('3mo', '1000d', ...); every other number is a parameter too."""
    if task not in PRESETS:
        raise ValueError(f"Unknown task '{task}'. Use one of {sorted(PRESETS)} or 'custom'.")
    p = {k: v for k, v in params.items() if v is not None}
    period = resolve_period(p.pop("period", None) or DEFAULT_PERIOD[task], today)
    if period.days > get_settings().max_period_days:
        raise ValueError(f"Period too long ({period.days} days); the maximum is {get_settings().max_period_days}.")
    need = {"technical": p.get("long_window", 0), "backtest": p.get("sma_window", 0)}.get(task, 0)
    if period.days < min_calendar_days(need) and need:
        raise ValueError(f"A {need}-day SMA needs at least {min_calendar_days(need)} calendar days of history; "
                         f"'{period.label}' is only {period.days}.")
    tickers = [normalize_ticker(t) for t in p.pop("tickers", [])]
    ticker = normalize_ticker(p.pop("ticker", ""))
    return PRESETS[task].format(
        ticker=ticker, tickers=", ".join(tickers), tickers_list=tickers,
        start=period.start.isoformat(), end=period.end.isoformat(), span=period.label, **p,
    )


async def code_interpreter(code: str) -> str:
    """Execute Python code and return its stdout/stderr. Use print() to show results."""
    r = await sandbox.run_python(code)
    return f"returncode={r['returncode']}\nSTDOUT:\n{r['stdout']}\nSTDERR:\n{r['stderr']}"


def build_agent(role: str = "analysis", system_prompt: str = SYSTEM_PROMPT, extra_tools=None):
    tools = [FunctionTool.from_defaults(async_fn=code_interpreter, name="code_interpreter")]
    return FunctionAgent(
        name="CodeAnalyst",
        description="An agent that writes and executes Python code for stock analysis",
        system_prompt=system_prompt,
        tools=tools + list(extra_tools or []),
        llm=get_llm(role, "llamaindex"),
    )


def response_text(result) -> str:
    """Join text blocks (models may emit thinking blocks first); fall back to str()."""
    blocks = getattr(getattr(result, "response", None), "blocks", None) or []
    text = "".join(getattr(b, "text", "") for b in blocks if hasattr(b, "text"))
    return (text or str(result)).replace("\\n", "\n")


async def run(prompt: str) -> str:
    return response_text(await build_agent().run(user_msg=prompt))
