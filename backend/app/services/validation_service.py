"""
Validation service.

Validates an uploaded financial-statement file (CSV or XLSX) BEFORE any
of it reaches the database or the Financial Analytics Engine. Two kinds
of failure are distinguished:

  - FILE-LEVEL errors (missing required columns, unreadable file, wrong
    file type): the whole upload is rejected, nothing is persisted.
  - ROW-LEVEL errors (a single row has a non-numeric value, a negative
    value where one isn't economically valid, a bad date range): that
    row is excluded and reported; the rest of the file still proceeds.
    This mirrors how a real user would want a 200-row upload to behave —
    one bad row shouldn't nuke the other 199.

No business logic (KPI computation, persistence) lives here — this
module's only job is: "is this row/file usable, and if not, why."
"""

from datetime import datetime
from typing import Dict, List, Tuple

import pandas as pd

from app.exceptions.custom_exceptions import ValidationError

# The full set of columns a valid upload must contain. Mirrors
# data/DATA_DICTIONARY.md exactly.
REQUIRED_COLUMNS = [
    "company_id",
    "company_name",
    "sector",
    "currency",
    "period_label",
    "period_start",
    "period_end",
    "revenue",
    "cogs",
    "operating_expenses",
    "interest_expense",
    "net_income",
    "current_assets",
    "current_liabilities",
    "inventory",
    "total_debt",
    "total_equity",
    "cash_and_equivalents",
    "operating_cash_flow",
    "oil_energy_exposure_pct",
    "import_cost_exposure_pct",
    "export_revenue_exposure_pct",
    "fx_debt_exposure_pct",
    "variable_rate_debt_pct",
    "demand_sensitivity_index",
    "variable_cost_ratio",
]

NUMERIC_COLUMNS = [
    "revenue",
    "cogs",
    "operating_expenses",
    "interest_expense",
    "net_income",
    "current_assets",
    "current_liabilities",
    "inventory",
    "total_debt",
    "total_equity",
    "cash_and_equivalents",
    "operating_cash_flow",
    "oil_energy_exposure_pct",
    "import_cost_exposure_pct",
    "export_revenue_exposure_pct",
    "fx_debt_exposure_pct",
    "variable_rate_debt_pct",
    "demand_sensitivity_index",
    "variable_cost_ratio",
]

# Columns that must be >= 0 (unlike e.g. net_income, which can legitimately
# be negative).
NON_NEGATIVE_COLUMNS = [
    "revenue",
    "current_assets",
    "current_liabilities",
    "inventory",
    "total_debt",
    "total_equity",
    "cash_and_equivalents",
]

# Exposure fields must be within [0, 1] (they're fractions/percentages).
EXPOSURE_PCT_COLUMNS = [
    "oil_energy_exposure_pct",
    "import_cost_exposure_pct",
    "export_revenue_exposure_pct",
    "fx_debt_exposure_pct",
    "variable_rate_debt_pct",
]

SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}


def read_upload(filename: str, file_bytes: bytes) -> pd.DataFrame:
    """
    Parse an uploaded CSV or XLSX file into a DataFrame. Raises
    ValidationError (file-level) for an unsupported extension or a file
    that can't be parsed at all.
    """
    lowered = filename.lower()
    if lowered.endswith(".csv"):
        try:
            import io
            return pd.read_csv(io.BytesIO(file_bytes))
        except Exception as exc:
            raise ValidationError(f"Could not parse '{filename}' as CSV: {exc}") from exc
    elif lowered.endswith(".xlsx"):
        try:
            import io
            return pd.read_excel(io.BytesIO(file_bytes))
        except Exception as exc:
            raise ValidationError(f"Could not parse '{filename}' as XLSX: {exc}") from exc
    else:
        raise ValidationError(
            f"Unsupported file type for '{filename}'. Only .csv and .xlsx are accepted."
        )


def validate_and_clean(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    Validate a parsed DataFrame against the required schema.

    Returns:
        (clean_df, row_errors) — clean_df contains only the rows that
        passed every check (with numeric columns coerced to float and
        dates validated); row_errors is a list of
        {"row_index": int, "company_id": str|None, "errors": [str, ...]}
        for every row that was excluded.

    Raises:
        ValidationError (file-level) if a required column is entirely
        missing, or if the file has zero data rows.
    """
    if df.empty:
        raise ValidationError("The uploaded file has no data rows.")

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_columns:
        raise ValidationError(
            f"Missing required column(s): {', '.join(missing_columns)}",
            details={"missing_columns": missing_columns},
        )

    df = df.copy()
    row_errors: List[Dict] = []
    valid_row_mask = []

    for idx, row in df.iterrows():
        errors = _validate_row(row)
        if errors:
            row_errors.append({
                "row_index": int(idx),
                "company_id": str(row.get("company_id", "")) or None,
                "period_label": str(row.get("period_label", "")) or None,
                "errors": errors,
            })
            valid_row_mask.append(False)
        else:
            valid_row_mask.append(True)

    clean_df = df[valid_row_mask].copy()

    if clean_df.empty:
        raise ValidationError(
            "Every row in the uploaded file failed validation — nothing to import.",
            details={"row_errors": row_errors},
        )

    # Coerce numeric columns now that we know they parse cleanly per-row.
    for col in NUMERIC_COLUMNS:
        clean_df[col] = pd.to_numeric(clean_df[col], errors="coerce")

    # String columns: strip whitespace for cleanliness/consistency.
    for col in ["company_id", "company_name", "sector", "currency", "period_label"]:
        clean_df[col] = clean_df[col].astype(str).str.strip()

    return clean_df.reset_index(drop=True), row_errors


def _validate_row(row: pd.Series) -> List[str]:
    """Return a list of human-readable error strings for one row (empty list = valid)."""
    errors: List[str] = []

    # Required string fields must be non-empty.
    for col in ["company_id", "company_name", "sector", "period_label"]:
        value = row.get(col)
        if pd.isna(value) or str(value).strip() == "":
            errors.append(f"'{col}' is required and cannot be empty.")

    # Numeric fields must actually parse as numbers.
    for col in NUMERIC_COLUMNS:
        value = row.get(col)
        if pd.isna(value):
            errors.append(f"'{col}' is missing.")
            continue
        try:
            float(value)
        except (TypeError, ValueError):
            errors.append(f"'{col}' must be numeric, got '{value}'.")

    if errors:
        # Don't bother with range checks if basic parsing already failed.
        return errors

    for col in NON_NEGATIVE_COLUMNS:
        if float(row[col]) < 0:
            errors.append(f"'{col}' cannot be negative (got {row[col]}).")

    for col in EXPOSURE_PCT_COLUMNS:
        value = float(row[col])
        if not (0.0 <= value <= 1.0):
            errors.append(f"'{col}' must be between 0 and 1 (got {value}).")

    if float(row["demand_sensitivity_index"]) < 0:
        errors.append("'demand_sensitivity_index' cannot be negative.")
    if not (0.0 <= float(row["variable_cost_ratio"]) <= 1.0):
        errors.append("'variable_cost_ratio' must be between 0 and 1.")

    if float(row["current_liabilities"]) == 0:
        errors.append("'current_liabilities' cannot be zero (Current Ratio would be undefined).")

    # Date sanity.
    try:
        start = datetime.fromisoformat(str(row["period_start"]))
        end = datetime.fromisoformat(str(row["period_end"]))
        if start > end:
            errors.append("'period_start' must not be after 'period_end'.")
    except ValueError:
        errors.append(
            f"'period_start'/'period_end' must be ISO dates (YYYY-MM-DD), "
            f"got '{row['period_start']}' / '{row['period_end']}'."
        )

    return errors
