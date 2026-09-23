"""
Tests for app/services/validation_service.py.

Uses the real demo dataset (data/company_financials.csv) as the "known
good" baseline, and constructs realistic malformed variants (via actual
CSV text editing, not in-memory dtype forcing, since pandas' strict
dtype handling doesn't allow assigning a string into an existing float64
Series in place — editing the CSV text is what a real bad upload looks
like anyway).
"""

from pathlib import Path

import pandas as pd
import pytest

from app.exceptions.custom_exceptions import ValidationError
from app.services.validation_service import read_upload, validate_and_clean

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def demo_df() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "company_financials.csv")


def test_full_demo_dataset_passes_cleanly(demo_df):
    clean_df, row_errors = validate_and_clean(demo_df)
    assert row_errors == []
    assert len(clean_df) == len(demo_df)


def test_missing_required_column_raises_file_level_error(demo_df):
    bad_df = demo_df.drop(columns=["revenue"])
    with pytest.raises(ValidationError) as exc_info:
        validate_and_clean(bad_df)
    assert "revenue" in exc_info.value.message


def test_empty_dataframe_raises_file_level_error():
    empty_df = pd.DataFrame()
    with pytest.raises(ValidationError):
        validate_and_clean(empty_df)


def test_negative_revenue_excludes_only_that_row(demo_df):
    lines = demo_df.to_csv(index=False).splitlines()
    header = lines[0].split(",")
    revenue_idx = header.index("revenue")
    row = lines[1].split(",")
    row[revenue_idx] = "-100"
    lines[1] = ",".join(row)
    csv_bytes = "\n".join(lines).encode("utf-8")

    reloaded = read_upload("bad.csv", csv_bytes)
    clean_df, row_errors = validate_and_clean(reloaded)

    assert len(row_errors) == 1
    assert len(clean_df) == len(demo_df) - 1
    assert "revenue" in row_errors[0]["errors"][0]


def test_non_numeric_value_excludes_only_that_row(demo_df):
    lines = demo_df.to_csv(index=False).splitlines()
    header = lines[0].split(",")
    cogs_idx = header.index("cogs")
    row = lines[3].split(",")
    row[cogs_idx] = "not_a_number"
    lines[3] = ",".join(row)
    csv_bytes = "\n".join(lines).encode("utf-8")

    reloaded = read_upload("bad.csv", csv_bytes)
    _clean_df, row_errors = validate_and_clean(reloaded)

    assert len(row_errors) == 1
    assert any("cogs" in e for e in row_errors[0]["errors"])


def test_exposure_pct_out_of_range_excludes_only_that_row(demo_df):
    lines = demo_df.to_csv(index=False).splitlines()
    header = lines[0].split(",")
    oil_idx = header.index("oil_energy_exposure_pct")
    row = lines[2].split(",")
    row[oil_idx] = "1.5"
    lines[2] = ",".join(row)
    csv_bytes = "\n".join(lines).encode("utf-8")

    reloaded = read_upload("bad.csv", csv_bytes)
    _clean_df, row_errors = validate_and_clean(reloaded)

    assert len(row_errors) == 1
    assert any("oil_energy_exposure_pct" in e for e in row_errors[0]["errors"])


def test_zero_current_liabilities_is_rejected(demo_df):
    lines = demo_df.to_csv(index=False).splitlines()
    header = lines[0].split(",")
    cl_idx = header.index("current_liabilities")
    row = lines[1].split(",")
    row[cl_idx] = "0"
    lines[1] = ",".join(row)
    csv_bytes = "\n".join(lines).encode("utf-8")

    reloaded = read_upload("bad.csv", csv_bytes)
    _clean_df, row_errors = validate_and_clean(reloaded)

    assert len(row_errors) == 1
    assert any("current_liabilities" in e for e in row_errors[0]["errors"])


def test_read_upload_rejects_unsupported_extension():
    with pytest.raises(ValidationError):
        read_upload("statement.pdf", b"not a real pdf")


def test_read_upload_handles_real_csv_and_xlsx_demo_files():
    csv_bytes = (DATA_DIR / "company_financials.csv").read_bytes()
    df_csv = read_upload("company_financials.csv", csv_bytes)
    assert len(df_csv) == 160

    xlsx_bytes = (DATA_DIR / "company_financials.xlsx").read_bytes()
    df_xlsx = read_upload("company_financials.xlsx", xlsx_bytes)
    assert len(df_xlsx) == 160
