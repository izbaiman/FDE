"""
Parses raw files (xlsx, pdf, eml/txt) into text chunks with metadata, ready
for embedding via app.retrieval.add_chunks.

Chunking strategy is deliberately simple and source-aware rather than a
single blind token-count splitter:
- Excel: one chunk per sheet, rendered as a readable row-by-row summary
  (splitting a table mid-row loses the meaning of the row).
- PDF: one chunk per "section" (split on blank-line-separated paragraphs,
  merged up to a max size), which keeps a section's argument together.
- Email: one chunk per email (they're already a natural unit, and short
  enough not to need splitting).
"""
import hashlib
from pathlib import Path

import pandas as pd
import pdfplumber

from app.retrieval import add_chunks

_MAX_CHUNK_CHARS = 1500


def _chunk_id(source_file: str, idx: int) -> str:
    return hashlib.sha1(f"{source_file}:{idx}".encode()).hexdigest()[:16]


def ingest_excel(path: Path) -> int:
    xls = pd.read_excel(path, sheet_name=None, header=None)
    n = 0
    for sheet_name, df in xls.items():
        text = f"Excel file: {path.name}, sheet: {sheet_name}\n\n"
        text += df.fillna("").astype(str).to_string(index=False, header=False)
        add_chunks(
            ids=[_chunk_id(f"{path.name}:{sheet_name}", 0)],
            texts=[text[: _MAX_CHUNK_CHARS * 2]],  # tables tolerate a larger cap
            metadatas=[{"source_type": "excel", "source_file": path.name, "sheet": sheet_name}],
        )
        n += 1
    return n


def ingest_pdf(path: Path) -> int:
    with pdfplumber.open(path) as pdf:
        full_text = "\n\n".join(page.extract_text() or "" for page in pdf.pages)

    paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) > _MAX_CHUNK_CHARS and current:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)

    ids = [_chunk_id(path.name, i) for i in range(len(chunks))]
    metadatas = [{"source_type": "pdf", "source_file": path.name, "chunk_index": i} for i in range(len(chunks))]
    add_chunks(ids=ids, texts=chunks, metadatas=metadatas)
    return len(chunks)


def ingest_email(path: Path) -> int:
    text = path.read_text(errors="ignore")
    add_chunks(
        ids=[_chunk_id(path.name, 0)],
        texts=[f"Email file: {path.name}\n\n{text}"],
        metadatas=[{"source_type": "email", "source_file": path.name}],
    )
    return 1


def ingest_directory(data_dir: Path) -> dict:
    """Walk a directory tree and ingest every recognized file type. Returns
    a summary count per source type for a quick sanity check."""
    summary = {"excel": 0, "pdf": 0, "email": 0, "skipped": 0}

    for path in sorted(data_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        try:
            if suffix in (".xlsx", ".xlsm"):
                summary["excel"] += ingest_excel(path)
            elif suffix == ".pdf":
                summary["pdf"] += ingest_pdf(path)
            elif suffix in (".eml", ".txt"):
                summary["email"] += ingest_email(path)
            else:
                summary["skipped"] += 1
        except Exception as e:
            print(f"Failed to ingest {path}: {e}")
            summary["skipped"] += 1

    return summary
