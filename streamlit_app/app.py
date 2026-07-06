"""
Streamlit front end for the Enterprise Data Copilot.

This is a thin client - all it does is call the FastAPI backend
(auth/token, /ask, /ingest, /health) over HTTP and render the response.
No business logic lives here; that's the point of keeping the API and UI
as separate layers, so you could swap this for a different front end (or
add a Slack bot, a CLI, etc.) without touching app/.

Run:
    streamlit run streamlit_app/app.py

Requires the FastAPI backend running separately (default: http://localhost:8000).
"""
import os

import requests
import streamlit as st

st.set_page_config(page_title="Enterprise Data Copilot", page_icon="📊", layout="wide")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "token" not in st.session_state:
    st.session_state.token = None
if "username" not in st.session_state:
    st.session_state.username = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # list of dicts: question, answer, reasoning, sql, sources
if "api_base" not in st.session_state:
    st.session_state.api_base = os.environ.get("API_BASE", "http://localhost:8000")


def api_url(path: str) -> str:
    return f"{st.session_state.api_base.rstrip('/')}{path}"


def auth_headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state.token}"}


# ---------------------------------------------------------------------------
# Sidebar: connection settings, login, health, ingest
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📊 Data Copilot")

    st.session_state.api_base = st.text_input(
        "API base URL", value=st.session_state.api_base, help="Where the FastAPI backend is running"
    )

    st.divider()

    # --- Health check ---
    try:
        health = requests.get(api_url("/health"), timeout=5)
        if health.ok:
            data = health.json()
            st.success(f"Backend online · {data.get('vector_store_chunks', '?')} chunks indexed")
        else:
            st.error(f"Backend returned {health.status_code}")
    except requests.exceptions.RequestException:
        st.error("Cannot reach backend. Is it running?")

    st.divider()

    # --- Login / logout ---
    if st.session_state.token is None:
        st.subheader("Sign in")
        with st.form("login_form"):
            username = st.text_input("Username", value="analyst")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)

        if submitted:
            try:
                resp = requests.post(
                    api_url("/auth/token"),
                    data={"username": username, "password": password},
                    timeout=10,
                )
                if resp.ok:
                    st.session_state.token = resp.json()["access_token"]
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("Login failed - check credentials.")
            except requests.exceptions.RequestException as e:
                st.error(f"Could not reach backend: {e}")
    else:
        st.success(f"Signed in as **{st.session_state.username}**")
        if st.button("Sign out", use_container_width=True):
            st.session_state.token = None
            st.session_state.username = None
            st.session_state.chat_history = []
            st.rerun()

        st.divider()

        # --- Document ingestion ---
        st.subheader("Documents")
        data_dir = st.text_input("Data directory (on the server)", value="./data")
        if st.button("Re-index documents", use_container_width=True):
            with st.spinner("Ingesting Excel/PDF/email files into the vector store..."):
                try:
                    resp = requests.post(
                        api_url("/ingest"),
                        params={"data_dir": data_dir},
                        headers=auth_headers(),
                        timeout=300,
                    )
                    if resp.ok:
                        result = resp.json()
                        st.success(
                            f"Indexed: {result['summary']} · "
                            f"total chunks now: {result['total_chunks_in_store']}"
                        )
                    else:
                        st.error(f"Ingest failed: {resp.status_code} {resp.text}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Could not reach backend: {e}")

        st.divider()
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()

# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------
st.title("Enterprise Data Copilot")
st.caption("Ask questions across SQL, Excel, PDFs, and emails. Every answer shows its sources.")

if st.session_state.token is None:
    st.info("Sign in from the sidebar to start asking questions.")
    st.stop()

SAMPLE_QUESTIONS = [
    "What were our top-selling products last quarter?",
    "Why did revenue drop in April 2026?",
    "Show me stores with declining sales.",
    "What's causing Riverside Commons to underperform?",
    "Did the March promotion affect April numbers?",
]

with st.expander("💡 Try a sample question"):
    cols = st.columns(len(SAMPLE_QUESTIONS))
    for col, q in zip(cols, SAMPLE_QUESTIONS):
        if col.button(q, use_container_width=True):
            st.session_state.pending_question = q

# --- Render chat history ---
for turn in st.session_state.chat_history:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        st.write(turn["answer"])
        with st.expander("How this was answered"):
            st.markdown(f"**Routing decision:** {turn['reasoning']}")
            if turn.get("sql_used"):
                st.markdown(f"**SQL executed** ({turn.get('sql_row_count', 0)} rows returned):")
                st.code(turn["sql_used"], language="sql")
            if turn.get("sources"):
                st.markdown("**Sources:**")
                for s in turn["sources"]:
                    st.markdown(f"- {s}")

# --- Handle a sample-question click or new input ---
question = st.chat_input("Ask a question about sales, stores, or trends...")
if "pending_question" in st.session_state:
    question = st.session_state.pop("pending_question")

if question:
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Routing, querying, and synthesizing an answer..."):
            try:
                resp = requests.post(
                    api_url("/ask"),
                    json={"question": question},
                    headers=auth_headers(),
                    timeout=120,
                )
            except requests.exceptions.RequestException as e:
                st.error(f"Could not reach backend: {e}")
                resp = None

        if resp is not None:
            if resp.status_code == 401:
                st.error("Session expired - please sign in again.")
                st.session_state.token = None
                st.rerun()
            elif resp.ok:
                result = resp.json()
                st.write(result["answer"])
                with st.expander("How this was answered"):
                    st.markdown(f"**Routing decision:** {result['routing_reasoning']}")
                    if result.get("sql_used"):
                        st.markdown(f"**SQL executed** ({result.get('sql_row_count', 0)} rows returned):")
                        st.code(result["sql_used"], language="sql")
                    if result.get("sources"):
                        st.markdown("**Sources:**")
                        for s in result["sources"]:
                            st.markdown(f"- {s}")

                st.session_state.chat_history.append({
                    "question": question,
                    "answer": result["answer"],
                    "reasoning": result["routing_reasoning"],
                    "sql_used": result.get("sql_used"),
                    "sql_row_count": result.get("sql_row_count"),
                    "sources": result.get("sources", []),
                })
            else:
                st.error(f"Request failed: {resp.status_code} {resp.text}")
