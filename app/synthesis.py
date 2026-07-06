"""
Final step: take whatever the router decided to gather - SQL rows,
retrieved document chunks, or both - and produce one coherent answer with
source attribution. This is also where the model is told explicitly not to
paper over gaps (e.g. if SQL ran but retrieval found nothing relevant).
"""
from app.llm_client import complete
from app.config import settings

_SYSTEM = """You are an enterprise data analyst assistant. You've been given
the results of a SQL query and/or excerpts from internal documents (Excel
reports, PDFs, emails) relevant to a user's question.

Write a clear, direct answer to the question using only the evidence
provided. Rules:
- Cite sources inline, e.g. "(source: Supply_Chain_Incident_Report_April2026.pdf)"
  or "(source: SQL query)".
- If the SQL results and document context suggest more than one contributing
  factor, mention all of them rather than picking the single most dramatic one.
- If the provided evidence doesn't fully answer the question, say so
  explicitly rather than filling the gap with a guess.
- Be concise. Lead with the direct answer, then the supporting detail.
"""


def synthesize(question: str, sql_result, retrieved_chunks: list[dict]) -> str:
    context_parts = [f"User question: {question}\n"]

    if sql_result is not None:
        if sql_result.error:
            context_parts.append(f"SQL query attempted:\n{sql_result.sql}\nError: {sql_result.error}")
        else:
            context_parts.append(
                f"SQL query:\n{sql_result.sql}\n\nResults ({len(sql_result.rows)} rows):\n{sql_result.rows}"
            )

    if retrieved_chunks:
        doc_context = "\n\n".join(
            f"[{c['metadata'].get('source_file', 'unknown')}]: {c['text'][:800]}"
            for c in retrieved_chunks
        )
        context_parts.append(f"Relevant document excerpts:\n{doc_context}")

    if sql_result is None and not retrieved_chunks:
        context_parts.append("No data sources were retrieved for this question.")

    user_message = "\n\n---\n\n".join(context_parts)
    return complete(system=_SYSTEM, user=user_message, model=settings.synthesis_model, max_tokens=800)
