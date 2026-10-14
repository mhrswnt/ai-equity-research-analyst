from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str
    name: str
    filename: str
    pages: int


class ChatRequest(BaseModel):
    question: str
    document_ids: list[str] = Field(min_length=1)
    top_k: int | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
