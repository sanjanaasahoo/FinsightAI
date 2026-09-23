"""
services package.

Deterministic core:
  - validation_service.py     : file/row validation for uploaded statements
  - ingestion_service.py       : upsert validated rows into SQLite
  - analytics_engine.py        : KPIs, Financial Health Score, trend analysis
  - scenario_assumptions.py    : documented, executed scenario transmission rules
  - scenario_engine.py         : applies each scenario to a statement
  - impact_engine.py           : Base vs Scenario comparison + most-affected ranking
  - ml_risk_service.py         : runtime inference over the trained risk model

None of the above depend on FastAPI or SQLAlchemy — every function takes
and returns plain dicts, which is what makes them independently
unit-testable (see ../../tests/).

Generative layer (the only module that calls an external API):
  - gemini_service.py          : explains already-computed results via
                                  the Gemini API; never calculates a
                                  financial number itself

RAG/document services are reserved for a later phase and are not present yet.
"""
