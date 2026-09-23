"""
Statements router — financial-statement upload (CSV/XLSX) and retrieval.
"""

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import FinancialStatement
from app.exceptions.custom_exceptions import NotFoundError, ValidationError
from app.schemas.statement_schema import RowError, StatementOut, UploadSummary
from app.services import ingestion_service, validation_service

router = APIRouter(prefix="/api/statements", tags=["Statements"])

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB — generous for a CSV/XLSX statement file


@router.post("/upload", response_model=UploadSummary)
async def upload_statements(
    file: UploadFile = File(..., description="A .csv or .xlsx financial-statement file."),
    db: Session = Depends(get_db),
):
    """
    Upload a CSV or XLSX file of company financial statements.

    The file may contain one or many companies and one or many reporting
    periods per company — every row is validated independently; rows
    that fail validation are skipped and reported in `row_errors` rather
    than failing the whole upload. Re-uploading a (company_id,
    period_label) that already exists overwrites it.
    """
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise ValidationError(
            f"File exceeds the {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB upload limit."
        )

    raw_df = validation_service.read_upload(file.filename, file_bytes)
    clean_df, row_errors = validation_service.validate_and_clean(raw_df)

    summary = ingestion_service.ingest_dataframe(db, clean_df, source_filename=file.filename)

    return UploadSummary(
        filename=file.filename,
        rows_rejected=len(row_errors),
        row_errors=[RowError(**e) for e in row_errors],
        **summary,
    )


@router.get("/{statement_id}", response_model=StatementOut)
def get_statement(statement_id: int, db: Session = Depends(get_db)):
    statement = db.query(FinancialStatement).filter(FinancialStatement.id == statement_id).one_or_none()
    if statement is None:
        raise NotFoundError(f"Statement {statement_id} not found.")
    return statement
