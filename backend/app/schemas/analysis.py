from typing import Literal

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    task: Literal["price_summary", "technical", "compare", "backtest", "custom"]
    ticker: str | None = Field(None, description="NSE ticker with .NS suffix, e.g. RELIANCE.NS")
    tickers: list[str] | None = Field(None, description="For task=compare")
    period: str | None = Field(None, description="History window: 1mo, 3mo, 6mo, 1y, 3y, 1000d, 12w or ytd "
                                                   "(calendar based). Defaults per task.")
    short_window: int = 20
    long_window: int = 50
    rsi_period: int = 14
    sma_window: int = 20
    prompt: str | None = Field(None, description="Free-form instruction for task=custom")


class AnalysisResponse(BaseModel):
    task: str
    prompt: str
    result: str
