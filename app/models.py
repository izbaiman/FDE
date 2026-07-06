from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    answer: str
    routing_reasoning: str
    sql_used: str | None = None
    sql_row_count: int | None = None
    sources: list[str] = []


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class IngestResponse(BaseModel):
    summary: dict
    total_chunks_in_store: int
