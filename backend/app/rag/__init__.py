"""
RAG package — Retrieval-Augmented Generation over an optional uploaded
financial PDF/annual report.

Sub-packages (per the architecture document's RAG Pipeline section):

  - ingestion/  : PDF text extraction (PyMuPDF) and chunking
  - embedding/  : chunk/query embedding via sentence-transformers
  - retrieval/  : local FAISS index build + top-k similarity search

Deliberately scoped small: one document at a time, one local FAISS index
per document, one retrieval hop. No multi-tenant vector storage, no
reranking, no agentic retrieval, no external vector-database server.

All modules in this package are intentionally empty in this phase
(infrastructure only) — implementation arrives in a later phase.
"""
