"""
seed_from_data.py — load data/company_financials.csv straight into the
local SQLite database, without going through the HTTP upload endpoint.

Useful for quickly getting a populated database for a demo/interview
without needing curl or Postman. This calls the exact same
validation_service + ingestion_service functions the API uses — it is
NOT a separate ingestion path, just a shortcut to it.

Usage (from backend/):
    python3 scripts/seed_from_data.py
    python3 scripts/seed_from_data.py --file ../data/company_financials.xlsx
"""

import argparse
import sys
from pathlib import Path

# Allow running this script directly (`python3 scripts/seed_from_data.py`)
# by ensuring the backend/ directory (which contains the `app` package)
# is on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import SessionLocal, init_db  # noqa: E402
from app.services import ingestion_service, validation_service  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed FinSight AI's database from a demo data file.")
    parser.add_argument(
        "--file",
        default=str(Path(__file__).resolve().parents[2] / "data" / "company_financials.csv"),
        help="Path to a company_financials.csv or .xlsx file (default: data/company_financials.csv).",
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Initializing database schema...")
    init_db()

    print(f"Reading {file_path}...")
    file_bytes = file_path.read_bytes()
    raw_df = validation_service.read_upload(file_path.name, file_bytes)
    clean_df, row_errors = validation_service.validate_and_clean(raw_df)

    if row_errors:
        print(f"WARNING: {len(row_errors)} row(s) failed validation and were skipped:")
        for err in row_errors[:10]:
            print(f"  - row {err['row_index']} ({err['company_id']}): {err['errors']}")

    db = SessionLocal()
    try:
        summary = ingestion_service.ingest_dataframe(db, clean_df, source_filename=file_path.name)
    finally:
        db.close()

    print()
    print("Seed complete:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
