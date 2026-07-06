"""
Text-to-SQL agent.

Flow: live schema -> LLM generates SQL -> validate_sql() sandboxes it ->
execute -> return rows + the SQL itself (always show your work - both for
user trust and for debugging when the model gets it wrong).
"""
from pydantic import BaseModel

from app.database import get_schema_description, run_safe_query, UnsafeQueryError
from app.llm_client import complete
from app.config import settings

_SYSTEM_TEMPLATE = """You are a SQL analyst. Given a database schema and a
question, write a single read-only SQL query (SQLite dialect) that answers
it as precisely as possible.

Schema:
{schema}

Rules:
- Only SELECT or WITH ... SELECT statements. Never write, alter, or delete data.
- Prefer explicit column lists over SELECT *.
- Use strftime('%Y-%m', sale_date) for month grouping, since sale_date is stored as text (YYYY-MM-DD).
- When asked about "last quarter" or relative time periods, compute them
  relative to the most recent date in the sales table, not today's date -
  this is a historical dataset, not a live feed.
- Always include a reasonable LIMIT unless the question clearly calls for an aggregate with few rows.
- Return ONLY the SQL query. No markdown fences, no explanation, no prose.
"""


class SQLResult(BaseModel):
    sql: str
    rows: list[dict]
    error: str | None = None


def answer_with_sql(intent: str) -> SQLResult:
    schema = get_schema_description()
    system = _SYSTEM_TEMPLATE.format(schema=schema)

    raw_sql = complete(system=system, user=intent, model=settings.sql_model, max_tokens=600)
    sql = raw_sql.strip().strip("`").strip()
    if sql.lower().startswith("sql"):
        sql = sql[3:].strip()

    try:
        rows = run_safe_query(sql)
        return SQLResult(sql=sql, rows=rows)
    except UnsafeQueryError as e:
        return SQLResult(sql=sql, rows=[], error=f"Query rejected by safety layer: {e}")
    except Exception as e:
        return SQLResult(sql=sql, rows=[], error=f"Query execution failed: {e}")
