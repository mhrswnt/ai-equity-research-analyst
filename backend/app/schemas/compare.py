from typing import Optional

from pydantic import BaseModel, Field


class RawFinancials(BaseModel):
    revenue: Optional[float] = Field(None, description="Extracted revenue (in crores INR)")
    operating_income: Optional[float] = Field(None, description="Extracted operating income (in crores INR)")
    eps: Optional[float] = Field(None, description="Extracted earnings per share")


class InitialFinancialDataOutput(BaseModel):
    company_name: str = Field(..., description="Company name")
    ticker: str = Field(..., description="Stock ticker symbol")
    report_date: str = Field(..., description="Date of the report")
    raw_financials: RawFinancials = Field(..., description="Structured raw financial metrics")


class FinancialModelOutput(BaseModel):
    revenue_projection: float = Field(..., description="Projected revenue for next year (crores INR)")
    growth_rate: float = Field(..., description="Expected revenue growth rate (%)")
    valuation_estimate: float = Field(..., description="Estimated enterprise value (crores INR)")
    summary: str = Field(..., description="Brief summary of the analysis")


class ComparativeAnalysisOutput(BaseModel):
    comparative_analysis: str = Field(..., description="Comparative analysis between companies")
    overall_recommendation: str = Field(..., description="Investment recommendation with rationale")


class FinalEquityResearchMemoOutput(BaseModel):
    company_a_name: str = ""
    company_b_name: str = ""
    company_a_model: FinancialModelOutput
    company_b_model: FinancialModelOutput
    comparative_analysis: ComparativeAnalysisOutput


class CompareRequest(BaseModel):
    document_id_a: str
    document_id_b: str
