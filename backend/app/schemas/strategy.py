from pydantic import BaseModel, Field


class StrategyRequest(BaseModel):
    document_id: str
    libraries: str = Field("pandas, numpy, and statsmodels", description="Libraries the generated code should use")
    instruction: str | None = None
    extract_query: str | None = Field(None, description="Override the strategy-extraction query")
    top_k: int = 8


class StrategyResponse(BaseModel):
    plan: str
    code: str
    raw: str
