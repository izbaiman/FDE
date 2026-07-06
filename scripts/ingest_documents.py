#!/usr/bin/env python3
"""
CLI ingestion entry point. Run this once after dropping the sample dataset
(or any real Excel/PDF/email files) into ./data, and again any time the
documents change.

Usage:
    python scripts/ingest_documents.py [data_dir]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest import ingest_directory
from app.retrieval import collection_count


def main():
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./data")
    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}")
        sys.exit(1)

    print(f"Ingesting documents from {data_dir} ...")
    summary = ingest_directory(data_dir)
    print(f"Done. {summary}")
    print(f"Total chunks now in vector store: {collection_count()}")


if __name__ == "__main__":
    main()
