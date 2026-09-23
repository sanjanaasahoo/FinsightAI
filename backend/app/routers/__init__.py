"""
routers package.

FastAPI route definitions:
  - statements_router.py  : CSV/XLSX upload, statement retrieval
  - companies_router.py   : company + per-company statement listing
  - analyses_router.py    : run/retrieve KPI + Health Score analysis, trend
  - scenarios_router.py   : scenario types, single-scenario simulation,
                             combined stress test, scenario retrieval
  - risk_router.py        : ML risk assessment (base case or a stored
                             scenario run), model-info endpoint
  - insights_router.py    : Gemini-powered executive summary + Q&A

RAG/document routers are reserved for a later phase and are not present yet.
"""
