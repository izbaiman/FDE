"""
Enterprise Data Copilot - FastAPI entry point.

Pipeline for POST /ask:
  1. auth: verify JWT (get_current_user dependency)
  2. route: LLM decides needs_sql / needs_retrieval (app.router_agent)
  3. gather: run SQL and/or vector retrieval as needed (app.sql_agent, app.retrieval)
  4. synthesize: combine into one cited answer (app.synthesis)

Run locally:
    uvicorn app.main:app --reload

Docs:
    http://localhost:8000/docs
"""
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import authenticate_user, create_access_token, get_current_user, TokenData
from app.ingest import ingest_directory
from app.models import AskRequest, AskResponse, IngestResponse, Token
from app.retrieval import query as retrieve, collection_count
from app.router_agent import route
from app.sql_agent import answer_with_sql
from app.synthesis import synthesize

app = FastAPI(
    title="Enterprise Data Copilot",
    description="Ask questions across SQL, Excel, PDF, and email data sources.",
    version="1.0.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "vector_store_chunks": collection_count()}


@app.post("/auth/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if not authenticate_user(form_data.username, form_data.password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return Token(access_token=create_access_token(form_data.username))


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest, user: TokenData = Depends(get_current_user)):
    decision = route(request.question)

    sql_result = None
    if decision.needs_sql:
        sql_result = answer_with_sql(decision.sql_intent or request.question)

    retrieved_chunks = []
    if decision.needs_retrieval:
        retrieved_chunks = retrieve(decision.retrieval_query or request.question, n_results=5)

    answer = synthesize(request.question, sql_result, retrieved_chunks)

    sources = sorted({c["metadata"].get("source_file", "unknown") for c in retrieved_chunks})
    if sql_result is not None and not sql_result.error:
        sources.append("SQL database")

    return AskResponse(
        question=request.question,
        answer=answer,
        routing_reasoning=decision.reasoning,
        sql_used=sql_result.sql if sql_result else None,
        sql_row_count=len(sql_result.rows) if sql_result else None,
        sources=sources,
    )


@app.post("/ingest", response_model=IngestResponse)
def ingest(data_dir: str = "./data", user: TokenData = Depends(get_current_user)):
    """
    Re-scan a directory of Excel/PDF/email files and (re)index them into the
    vector store. Protected the same as /ask for the demo; in production
    this should require an admin role, not just any authenticated user.
    """
    path = Path(data_dir)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {data_dir}")
    summary = ingest_directory(path)
    return IngestResponse(summary=summary, total_chunks_in_store=collection_count())
