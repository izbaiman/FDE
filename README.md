# Enterprise Data Copilot

An AI assistant that answers business questions by routing across a SQL
database, Excel reports, PDFs, and emails — and knows which ones it needs
for a given question instead of blindly RAG-ing over everything.

Ships pre-loaded with the **Northwind Retail Co.** sample dataset (18 months
of sales data, plus documents explaining two real, discoverable business
events) so you can run this end to end without sourcing your own data first.

## Architecture

```
Question
   │
   ▼
POST /ask  (JWT-protected)
   │
   ▼
Router (LLM) ──► decides: needs_sql? needs_retrieval?
   │                              │
   ▼                              ▼
Text-to-SQL agent          Vector retrieval (Chroma)
 - live schema introspection - embeds question
 - LLM generates SQL          - top-k chunks from Excel/PDF/email
 - validated (SELECT-only,
   keyword blocklist, LIMIT)
 - executed against DB
   │                              │
   └──────────────┬───────────────┘
                   ▼
         Synthesis (LLM) ──► one answer, cited sources
```

The router is the piece that matters most here: "top-selling products" is
pure SQL, "why did revenue drop" needs SQL *and* documents, and getting that
routing decision right (and testable — see `tests/test_eval.py`) is most of
the engineering value in a project like this.

## Project layout

```
app/
  main.py          FastAPI app: /auth/token, /ask, /ingest, /health
  config.py        Settings (env-driven)
  auth.py          JWT issuance/verification
  database.py      Schema introspection + sandboxed SQL execution
  sql_agent.py     Text-to-SQL generation
  router_agent.py  SQL vs retrieval vs hybrid routing decision
  retrieval.py     Chroma vector store wrapper
  ingest.py        Excel/PDF/email -> chunks -> embeddings
  synthesis.py     Combines SQL + retrieved chunks into a cited answer
  models.py        Pydantic request/response schemas
scripts/
  ingest_documents.py   CLI to (re)index ./data into the vector store
streamlit_app/
  app.py           Streamlit front end (thin client, calls the API over HTTP)
tests/
  test_eval.py     End-to-end eval harness (not mocked unit tests)
data/              Sample dataset — SQLite DB, Excel, PDFs, emails
```

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY at minimum
```

The first run of `sentence-transformers` will download the embedding model
(`all-MiniLM-L6-v2`, ~80MB) — this requires network access once, then it's
cached locally.

## Run

**1. Ingest the sample documents into the vector store** (one-time, or
whenever documents change):

```bash
python scripts/ingest_documents.py ./data
```

**2. Start the API:**

```bash
uvicorn app.main:app --reload
```

**3. Start the Streamlit front end** (in a second terminal):

```bash
streamlit run streamlit_app/app.py
```

Opens at `http://localhost:8501`. Sign in with the demo credentials from
`.env` (`analyst` / `changeme123` by default), then ask a question — try
one of the sample-question buttons first. Every answer shows an expandable
"How this was answered" panel with the routing decision, the exact SQL
that ran, and which documents were cited, so you can demo *why* the system
answered the way it did, not just the answer itself.

The Streamlit app is a thin client: it only calls the FastAPI backend over
HTTP (`/auth/token`, `/ask`, `/ingest`, `/health`). No pipeline logic lives
in `streamlit_app/`, so you could swap it for a different UI (Slack bot,
CLI) without touching `app/`.

**4. Or skip the terminal juggling — curl it directly:**

```bash
curl -X POST http://localhost:8000/auth/token \
  -d "username=analyst&password=changeme123"
# -> {"access_token": "...", "token_type": "bearer"}

curl -X POST http://localhost:8000/ask \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"question": "Why did revenue drop in April 2026?"}'
```

Interactive API docs (Swagger UI): `http://localhost:8000/docs`

## Run with Docker

```bash
docker compose up --build
```

Starts both services:
- API: `http://localhost:8000`
- Streamlit UI: `http://localhost:8501` (pre-configured to reach the API
  container by its compose service name, `copilot-api`, not `localhost`)

Data and the vector store are mounted as volumes so they persist across
container restarts and can be edited without a rebuild.

## Testing

```bash
pytest tests/test_eval.py -v
```

This is an **eval harness**, not a mocked unit test suite — it calls the
real router, SQL agent, retrieval, and synthesis end to end, and asserts on
structural properties (did it route correctly, did the SQL execute without
error, does the answer mention the right root cause) rather than exact
string matches, since LLM output isn't deterministic enough for that. It
requires `ANTHROPIC_API_KEY` set and the vector store already ingested.

## Switching from SQLite to SQL Server

This ships with SQLite (`data/northwind_retail.db`) so it runs with zero
external dependencies. To point at real SQL Server:

1. `pip install pyodbc`
2. Set in `.env`:
   ```
   DATABASE_URL=mssql+pyodbc://readonly_user:password@your-server/YourDB?driver=ODBC+Driver+18+for+SQL+Server
   ```
3. Use a **read-only** DB user/role for `readonly_user` — this is your real
   security boundary in production, on top of (not instead of) the
   application-level SQL validation in `app/database.py`.

No other code changes needed — `get_schema_description()` introspects
whatever database it's pointed at.

## Security notes (what's real vs. what's demo-only)

- **Real:** SQL validation (`validate_sql`) rejects anything that isn't a
  single read-only `SELECT`/`WITH` statement, blocks DDL/DML keywords, and
  enforces a row limit. This runs on every LLM-generated query before
  execution, regardless of what the model was asked to do.
- **Demo-only:** `auth.py` checks credentials against two `.env` values.
  Swap `authenticate_user` for a real user table with hashed passwords
  (`passlib`) or your company's SSO/OIDC provider before this is
  internet-facing.
- **Worth adding before production:** per-user query rate limiting, an
  audit log of every generated SQL statement (who asked what, what ran),
  and role-based data access (e.g. a regional manager shouldn't be able to
  ask about other regions' data) enforced at the SQL layer, not just the
  prompt layer — prompts are not an access control mechanism.

## Extending

- **Add a data source:** write a new `ingest_x()` function in `app/ingest.py`
  following the pattern in `ingest_pdf`/`ingest_email`, then wire the file
  extension into `ingest_directory`.
- **Improve routing:** `tests/test_eval.py` is your regression suite — add
  a case for any question type you want the router to handle correctly
  before you touch the router prompt.
- **Swap the vector DB:** `app/retrieval.py` is the only file that touches
  Chroma directly; swapping to pgvector/Pinecone/Weaviate means changing
  this one file's internals, not the interface (`add_chunks`, `query`).
