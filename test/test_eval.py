"""
Lightweight eval harness, not a mocked unit test suite.

These tests hit the real pipeline (router -> SQL/retrieval -> synthesis)
end to end, which means they require ANTHROPIC_API_KEY to be set and the
vector store to already be ingested (run scripts/ingest_documents.py first).

This is intentionally a smoke/eval suite, not a correctness oracle: for
open-ended LLM answers, assert on *structural* properties you can check
deterministically (did it route correctly, did it cite a source, is a
number in a sane range) rather than exact string matches, which will be
brittle against any model or prompt change.

Run:
    pytest tests/test_eval.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.router_agent import route
from app.sql_agent import answer_with_sql
from app.retrieval import query as retrieve
from app.synthesis import synthesize

CASES = [
    {
        "question": "What were our top-selling products last quarter by revenue?",
        "expect_sql": True,
        "expect_retrieval": False,
    },
    {
        "question": "Why did revenue drop in April 2026?",
        "expect_sql": True,
        "expect_retrieval": True,
        "expect_answer_mentions_any": ["AeroFit", "Vertex", "stockout", "promo"],
    },
    {
        "question": "Show me stores with declining sales in 2026.",
        "expect_sql": True,
        "expect_retrieval": False,
    },
    {
        "question": "What's causing Riverside Commons to underperform?",
        "expect_sql": True,
        "expect_retrieval": True,
        "expect_answer_mentions_any": ["TrailBlazer", "competitor", "Riverside"],
    },
    {
        "question": "Did the March 2026 promotion affect April numbers?",
        "expect_sql": False,
        "expect_retrieval": True,
        "expect_answer_mentions_any": ["promo", "March", "pull"],
    },
]


@pytest.mark.parametrize("case", CASES, ids=[c["question"] for c in CASES])
def test_routing_and_answer(case):
    decision = route(case["question"])
    assert decision.needs_sql == case["expect_sql"], (
        f"Routing mismatch on needs_sql: {decision.reasoning}"
    )
    assert decision.needs_retrieval == case["expect_retrieval"], (
        f"Routing mismatch on needs_retrieval: {decision.reasoning}"
    )

    sql_result = answer_with_sql(decision.sql_intent or case["question"]) if decision.needs_sql else None
    chunks = retrieve(decision.retrieval_query or case["question"]) if decision.needs_retrieval else []

    if sql_result is not None:
        assert sql_result.error is None, f"SQL failed: {sql_result.error}\nSQL: {sql_result.sql}"

    answer = synthesize(case["question"], sql_result, chunks)
    assert len(answer) > 0

    expected_terms = case.get("expect_answer_mentions_any")
    if expected_terms:
        assert any(term.lower() in answer.lower() for term in expected_terms), (
            f"Answer didn't mention any of {expected_terms}:\n{answer}"
        )


def test_sql_safety_rejects_write_queries():
    from app.database import validate_sql, UnsafeQueryError

    with pytest.raises(UnsafeQueryError):
        validate_sql("DELETE FROM sales WHERE 1=1")

    with pytest.raises(UnsafeQueryError):
        validate_sql("SELECT * FROM sales; DROP TABLE sales;")

    # a plain SELECT should pass through unchanged (plus an added LIMIT)
    safe = validate_sql("SELECT * FROM stores")
    assert safe.lower().startswith("select")
    assert "limit" in safe.lower()
