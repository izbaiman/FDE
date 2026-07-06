"""
Database access layer.

Two responsibilities live here on purpose, side by side:
1. Schema introspection - so the text-to-SQL prompt always describes the
   *real* current schema instead of a hardcoded string that drifts.
2. Sandboxed execution - every generated query passes through
   `run_safe_query`, which is the actual security boundary. Nothing else
   in this codebase should call the raw engine directly.
"""
import re
import sqlparse
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.config import settings

engine: Engine = create_engine(settings.database_url, pool_pre_ping=True)

# Only these statement types are ever allowed to execute. Everything else
# (INSERT/UPDATE/DELETE/DROP/ALTER/ATTACH/PRAGMA writes/etc.) is rejected
# before it touches the database.
_ALLOWED_START = {"select", "with"}
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|grant|revoke|"
    r"exec|execute|truncate|replace|pragma|vacuum)\b",
    re.IGNORECASE,
)


class UnsafeQueryError(Exception):
    pass


def get_schema_description() -> str:
    """Render the live DB schema as compact text for the LLM prompt."""
    inspector = inspect(engine)
    lines = []
    for table_name in inspector.get_table_names():
        cols = inspector.get_columns(table_name)
        col_desc = ", ".join(f"{c['name']} {c['type']}" for c in cols)
        lines.append(f"TABLE {table_name}({col_desc})")

        fks = inspector.get_foreign_keys(table_name)
        for fk in fks:
            if fk.get("constrained_columns") and fk.get("referred_table"):
                lines.append(
                    f"  FK: {table_name}.{fk['constrained_columns'][0]} -> "
                    f"{fk['referred_table']}.{fk['referred_columns'][0]}"
                )
    return "\n".join(lines)


def validate_sql(sql: str) -> str:
    """
    Defense-in-depth validation of LLM-generated SQL before execution:
    - must be a single statement
    - must start with SELECT or WITH (read-only)
    - must not contain any DDL/DML/admin keywords, even inside a CTE
    - enforces a row LIMIT if the model didn't add one
    Raises UnsafeQueryError if any check fails.
    """
    statements = [s for s in sqlparse.split(sql) if s.strip()]
    if len(statements) != 1:
        raise UnsafeQueryError("Only a single SQL statement is allowed.")

    stmt = statements[0].strip().rstrip(";")
    first_token = stmt.strip().split(None, 1)[0].lower() if stmt.strip() else ""
    if first_token not in _ALLOWED_START:
        raise UnsafeQueryError(f"Query must start with SELECT or WITH, got '{first_token}'.")

    if _FORBIDDEN_KEYWORDS.search(stmt):
        raise UnsafeQueryError("Query contains a forbidden keyword (non-read-only operation).")

    if not re.search(r"\blimit\b", stmt, re.IGNORECASE):
        stmt = f"{stmt}\nLIMIT {settings.sql_max_rows}"

    return stmt


def run_safe_query(sql: str) -> list[dict]:
    """Validate then execute a read-only query, capped in size and time.

    Note: SQLAlchemy's `execution_options(timeout=...)` is honored by some
    DBAPI drivers (e.g. pyodbc/SQL Server) and ignored by others (e.g.
    sqlite3). For a hard guarantee on every backend, run this call inside
    a worker with its own timeout (e.g. `concurrent.futures.ThreadPoolExecutor`
    + `future.result(timeout=...)`), or rely on server-side statement
    timeouts (SQL Server's `SET LOCK_TIMEOUT` / query governor / a
    role-level resource limit) as the real enforcement point in production.
    """
    safe_sql = validate_sql(sql)
    with engine.connect() as conn:
        conn = conn.execution_options(timeout=settings.sql_timeout_seconds)
        result = conn.execute(text(safe_sql))
        columns = result.keys()
        rows = result.fetchmany(settings.sql_max_rows)
        return [dict(zip(columns, row)) for row in rows]
