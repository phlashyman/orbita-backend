"""
Bank statements router for Orbita.

Provides endpoints for importing bank statement lines, listing them,
and updating their status. All endpoints are scoped to the current user's
family (multi-tenant).
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.bank_statement import BankStatement, StatementStatus
from app.models.user import User
from app.schemas import (
    BankStatementImport,
    BankStatementLine,
    BankStatementRead,
    StatementStatusUpdate,
)
from app.services.statement_parser import parse_statement
from app.services.auto_matcher import find_matches, apply_auto_matches

router = APIRouter(prefix="/statements", tags=["Bank Statements"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_statement_or_404(
    db: AsyncSession,
    statement_id: UUID,
    family_id: UUID,
) -> BankStatement:
    """Fetch a bank statement line by ID ensuring it belongs to the given family."""
    result = await db.execute(
        select(BankStatement).where(
            BankStatement.id == statement_id,
            BankStatement.family_id == family_id,
        )
    )
    statement = result.scalar_one_or_none()
    if statement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank statement line not found",
        )
    return statement


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_statement_lines(
    body: BankStatementImport,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Import bank statement lines.

    Validates that all lines have unique ``bank_transaction_id`` values within
    the account. Skips duplicates that violate the unique constraint on
    ``(account_id, bank_transaction_id)``.

    Returns the count of imported and skipped lines.
    """
    # Validate uniqueness of bank_transaction_id within the import batch
    seen_ids = set()
    for line in body.lines:
        if line.bank_transaction_id in seen_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Duplicate bank_transaction_id "
                    f"'{line.bank_transaction_id}' in import batch"
                ),
            )
        seen_ids.add(line.bank_transaction_id)

    imported_count = 0
    skipped_count = 0

    for line in body.lines:
        stmt_line = BankStatement(
            family_id=current_user.family_id,
            account_id=body.account_id,
            bank_transaction_id=line.bank_transaction_id,
            amount=line.amount,
            date=line.date,
            description_raw=line.description_raw,
            status=StatementStatus.UNMATCHED.value,
        )
        db.add(stmt_line)

        try:
            await db.flush()
            imported_count += 1
        except IntegrityError:
            # Duplicate (account_id, bank_transaction_id) — skip
            await db.rollback()
            skipped_count += 1

    return {
        "imported_count": imported_count,
        "skipped_count": skipped_count,
    }


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_statement_file(
    account_id: UUID,
    file: UploadFile = File(..., description="Bank statement file (CSV, OFX, TXT)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload and parse a bank statement file.

    Supports CSV (semicolon or comma delimited) and OFX formats.
    Auto-detects Angolan bank formats (BAI, BFA, BCI, etc.).
    After parsing, imports all valid lines and triggers auto-matching.
    """
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided",
        )

    # Read file content
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    # Parse the file
    try:
        parsed_lines = parse_statement(
            file_content=content,
            filename=file.filename,
            account_id=str(account_id),
            family_id=str(current_user.family_id),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse file: {str(e)}",
        )

    if not parsed_lines:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid transactions found in file",
        )

    # Import lines
    imported_count = 0
    skipped_count = 0

    for line in parsed_lines:
        stmt_line = BankStatement(
            family_id=current_user.family_id,
            account_id=account_id,
            bank_transaction_id=line["bank_transaction_id"],
            amount=line["amount"],
            date=line["date"],
            description_raw=line["description_raw"],
            status=StatementStatus.UNMATCHED.value,
        )
        db.add(stmt_line)

        try:
            await db.flush()
            imported_count += 1
        except IntegrityError:
            await db.rollback()
            skipped_count += 1

    # Auto-match after import
    auto_matched = 0
    suggestions = 0
    try:
        from app.models.transaction import TransactionManual, TransactionStatus as TxStatus
        from sqlalchemy import select as sa_select

        # Get pending transactions
        tx_result = await db.execute(
            sa_select(TransactionManual).where(
                TransactionManual.family_id == current_user.family_id,
                TransactionManual.status == TxStatus.PENDING.value,
                TransactionManual.deleted_at.is_(None),
            )
        )
        pending_txs = tx_result.scalars().all()

        # Get unmatched statements for this account
        stmt_result = await db.execute(
            sa_select(BankStatement).where(
                BankStatement.family_id == current_user.family_id,
                BankStatement.account_id == account_id,
                BankStatement.status == StatementStatus.UNMATCHED.value,
            )
        )
        unmatched_stmts = stmt_result.scalars().all()

        if pending_txs and unmatched_stmts:
            match_result = find_matches(unmatched_stmts, pending_txs)
            auto_matched = len(match_result["auto_matches"])
            suggestions = len(match_result["suggestions"])
    except Exception:
        # Auto-match is best-effort
        pass

    return {
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "auto_matched": auto_matched,
        "suggestions": suggestions,
        "parsed_lines": len(parsed_lines),
    }


# ---------------------------------------------------------------------------
# List & Retrieve
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[BankStatementRead])
async def list_statement_lines(
    account_id: UUID | None = Query(None, description="Filter by bank account ID"),
    status_filter: StatementStatus | None = Query(
        None, alias="status", description="Filter by statement status"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List bank statement lines for the current user's family.

    Supports filtering by account and status.
    """
    query = select(BankStatement).where(
        BankStatement.family_id == current_user.family_id,
    )

    if account_id is not None:
        query = query.where(BankStatement.account_id == account_id)
    if status_filter is not None:
        query = query.where(BankStatement.status == status_filter.value)

    result = await db.execute(query)
    statements = result.scalars().all()
    return statements


@router.get("/{statement_id}", response_model=BankStatementRead)
async def get_statement_line(
    statement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single bank statement line by ID (family-scoped)."""
    statement = await _get_statement_or_404(
        db, statement_id, current_user.family_id
    )
    return statement


# ---------------------------------------------------------------------------
# Update status
# ---------------------------------------------------------------------------

@router.put("/{statement_id}/status", response_model=BankStatementRead)
async def update_statement_status(
    statement_id: UUID,
    body: StatementStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update the status of a bank statement line and optionally assign it
    to a family member for clarification.
    """
    statement = await _get_statement_or_404(
        db, statement_id, current_user.family_id
    )

    statement.status = body.status.value
    if body.assigned_user_id is not None:
        statement.assigned_user_id = body.assigned_user_id

    return statement
