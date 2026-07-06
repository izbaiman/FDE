"""
Routing layer: decides, for a given natural-language question, whether it
needs structured SQL lookup, unstructured retrieval (RAG over Excel/PDF/
email), or both.

This is the piece that separates a real copilot from "RAG over everything":
"top-selling products" is pure SQL, "why did revenue drop" is SQL (to
confirm/quantify the drop) *and* retrieval (to explain the cause), and a
router has to make that call before either sub-system runs.
"""
from pydantic import BaseModel

from app.llm_client import complete_json
from app.config import settings

_SYSTEM = """You are a query router for an enterprise data copilot. Given a
user question about a retail business, decide what data sources are needed
to answer it well.

The business has:
- A SQL database with tables: regions, stores, suppliers, products, sales,
  inventory_events (structured facts: revenue, quantities, trends over time)
- Unstructured documents: Excel reports, PDFs (incident reports, business
  reviews, competitive memos), and emails (operational discussion, root
  causes, context that never makes it into a database column)

Rules of thumb:
- Questions about numbers, rankings, totals, trends over time, comparisons
  between stores/products/regions -> need SQL.
- Questions asking "why" something happened, root causes, or context behind
  a number -> need retrieval (SQL too, if a number needs to be confirmed
  first).
- If unsure, prefer including both rather than guessing wrong and giving an
  incomplete answer.

Respond with JSON only, no other text, in exactly this shape:
{
  "needs_sql": true/false,
  "needs_retrieval": true/false,
  "sql_intent": "<clear restatement of what SQL should compute, or null>",
  "retrieval_query": "<search query for the document store, or null>",
  "reasoning": "<one sentence explaining the routing decision>"
}
"""


class RoutingDecision(BaseModel):
    needs_sql: bool
    needs_retrieval: bool
    sql_intent: str | None
    retrieval_query: str | None
    reasoning: str


def route(question: str) -> RoutingDecision:
    result = complete_json(
        system=_SYSTEM,
        user=question,
        model=settings.router_model,  # This is sending the wrong name
        max_tokens=400
    )
    return RoutingDecision(**result)
