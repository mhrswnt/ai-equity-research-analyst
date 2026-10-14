from pydantic import BaseModel


class ResearchRequest(BaseModel):
    topic: str


class ResearchResponse(BaseModel):
    report_content: str
    review: str
    research_notes: dict[str, str]
