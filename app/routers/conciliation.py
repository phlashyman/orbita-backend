"""
Conciliation router for Orbita.

Provides endpoints for reconciling manual transactions with bank statement
lines: viewing status, manual matching, unmatching, assignment, auto-matching,
and getting match suggestions. All endpoints are scoped to the current user's
family (multi-tenant).
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user, require_admin
from app.models.bank_statement import BankStatement, StatementStatus
from app.models.conciliation import ConciliationLog
from app.models.transaction import TransactionManual, TransactionStatus
from app.models.user import User
from app.schemas import (
    MatchRequest,
    MatchResult,
    MatchScore,
    UnmatchRequest,
)
from app.services import (
    ConciliationError,
    NotFoundError,
    apply_auto_matches,
    assign_statement_to_user,
    calculate_match_score,
    create_manual_match,
    find_matches,
    get_reconciliation_status,
    unmatch,
)

router = APIRouter(prefix="/conciliation", tags=["Conciliation"])


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_status(
    account_id: UUID | None = Query(
        None, description="Optional: filter by specific bank account"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get reconciliation status summary for the current user's family.

    Returns counts of total transactions, matched, unmatched, and items
    requiring reconciliation. Optionally filtered by a single bank account.
    """
    status_summary = await get_reconciliation_status(
        db=db,
        family_id=str(current_user.family_id),
        account_id=str(account_id) if account_id else None,
    )
    return status_summary


# ---------------------------------------------------------------------------
# Manual match
# ---------------------------------------------------------------------------

@router.post("/match", response_model=MatchResult, status_code=status.HTTP_201_CREATED)
async def manual_match(
    body: MatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Manually match a transaction with a bank statement line.

    Creates a conciliation log entry and updates both the transaction
    (status -> CONCILED) and statement line (status -> MATCHED).
    """
    try:
        log = await create_manual_match(
            db=db,
            family_id=str(current_user.family_id),
            transaction_manual_id=str(body.transaction_manual_id),
            bank_statement_id=str(body.bank_statement_id),
            conciliated_by=str(current_user.id),
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConciliationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Match failed: {exc}",
        ) from exc

    # Fetch related data for response
    tx_result = await db.execute(
        select(TransactionManual).where(
            TransactionManual.id == body.transaction_manual_id
        )
    )
    tx = tx_result.scalar_one()

    stmt_result = await db.execute(
        select(BankStatement).where(
            BankStatement.id == body.bank_statement_id
        )
    )
    stmt = stmt_result.scalar_one()

    return MatchResult(
        id=log.id,
        family_id=log.family_id,
        transaction_manual_id=log.transaction_manual_id,
        bank_statement_id=log.bank_statement_id,
        conciliated_by=log.conciliated_by,
        conciliated_at=log.conciliated_at,
        transaction_amount=str(tx.amount),
        transaction_date=tx.date,
        transaction_description=tx.description,
        statement_amount=str(stmt.amount),
        statement_date=stmt.date,
        statement_description_raw=stmt.description_raw,
    )


# ---------------------------------------------------------------------------
# Unmatch
# ---------------------------------------------------------------------------

@router.delete("/unmatch", status_code=status.HTTP_204_NO_CONTENT)
async def delete_match(
    body: UnmatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Undo a match by removing the conciliation log entry.

    Reverts both the manual transaction (status -> PENDING) and the bank
    statement line (status -> UNMATCHED).
    """
    try:
        await unmatch(db=db, conciliation_log_id=str(body.conciliation_log_id))
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConciliationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Unmatch failed: {exc}",
        ) from exc

    return None


# ---------------------------------------------------------------------------
# Assign statement to family member
# ---------------------------------------------------------------------------

class AssignRequest:
    """Request body for assigning a statement line to a family member."""

    def __init__(
        self,
        statement_id: UUID,
        user_id: UUID,
    ):
        self.statement_id = statement_id
        self.user_id = user_id


@router.post("/assign", status_code=status.HTTP_200_OK)
async def assign_statement(
    statement_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Assign an unmatched bank statement line to a family member for
    clarification.

    Updates the statement's status to ``RECONCILIATION_REQUIRED`` and sets
    ``assigned_user_id`` to the given user.
    """
    try:
        stmt = await assign_statement_to_user(
            db=db,
            statement_id=str(statement_id),
            user_id=str(user_id),
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConciliationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Assignment failed: {exc}",
        ) from exc

    return {
        "id": stmt.id,
        "status": stmt.status,
        "assigned_user_id": stmt.assigned_user_id,
        "message": "Statement assigned successfully",
    }


# ---------------------------------------------------------------------------
# Auto-match (admin only)
# ---------------------------------------------------------------------------

@router.post("/auto-match", status_code=status.HTTP_200_OK)
async def auto_match(
    account_id: UUID | None = Query(
        None, description="Optional: limit auto-match to a specific account"
    ),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Run the auto-matching engine on pending items for the family.

    Finds all unmatched statement lines and pending manual transactions,
    calculates match scores, and automatically applies matches with a
    score >= 80 (AUTO threshold).

    Requires ADMIN role.
    """
    # Fetch pending items for the family
    stmt_filter = [
        BankStatement.family_id == admin.family_id,
        BankStatement.status == StatementStatus.UNMATCHED.value,
    ]
    tx_filter = [
        TransactionManual.family_id == admin.family_id,
        TransactionManual.status == TransactionStatus.PENDING.value,
        TransactionManual.deleted_at.is_(None),
    ]

    if account_id is not None:
        stmt_filter.append(BankStatement.account_id == account_id)
        tx_filter.append(TransactionManual.account_id == account_id)

    stmt_result = await db.execute(select(BankStatement).where(*stmt_filter))
    statement_lines = stmt_result.scalars().all()

    tx_result = await db.execute(select(TransactionManual).where(*tx_filter))
    manual_transactions = tx_result.scalars().all()

    if not statement_lines or not manual_transactions:
        return {
            "auto_matched": 0,
            "suggestions": 0,
            "unmatched_statements": len(statement_lines),
            "pending_transactions": len(manual_transactions),
            "message": "No pending items to match",
        }

    # Run matching engine
    match_results = find_matches(
        statement_lines=list(statement_lines),
        manual_transactions=list(manual_transactions),
    )

    auto_matches = match_results.get("auto_matches", [])
    suggestions = match_results.get("suggestions", [])

    # Apply auto matches
    applied_logs = []
    if auto_matches:
        try:
            applied_logs = await apply_auto_matches(
                matches=auto_matches,
                db_session=db,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Auto-match application failed: {exc}",
            ) from exc

    return {
        "auto_matched": len(applied_logs),
        "suggestions": len(suggestions),
        "unmatched_statements": len(match_results.get("unmatched", [])),
        "pending_transactions": len(manual_transactions),
        "message": (
            f"Auto-matched {len(applied_logs)} items, "
            f"{len(suggestions)} suggestions available"
        ),
    }


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

@router.get("/suggestions")
async def get_suggestions(
    account_id: UUID | None = Query(
        None, description="Optional: limit suggestions to a specific account"
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of suggestions"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get matching suggestions for unmatched statement lines.

    Returns scored suggestions (score 50-79) and auto matches (score >= 80)
    for each unmatched bank statement line against pending manual transactions.
    """
    # Fetch pending items
    stmt_filter = [
        BankStatement.family_id == current_user.family_id,
        BankStatement.status == StatementStatus.UNMATCHED.value,
    ]
    tx_filter = [
        TransactionManual.family_id == current_user.family_id,
        TransactionManual.status == TransactionStatus.PENDING.value,
        TransactionManual.deleted_at.is_(None),
    ]

    if account_id is not None:
        stmt_filter.append(BankStatement.account_id == account_id)
        tx_filter.append(TransactionManual.account_id == account_id)

    stmt_result = await db.execute(select(BankStatement).where(*stmt_filter))
    statement_lines = stmt_result.scalars().all()

    tx_result = await db.execute(select(TransactionManual).where(*tx_filter))
    manual_transactions = tx_result.scalars().all()

    if not statement_lines or not manual_transactions:
        return {
            "suggestions": [],
            "auto_matches": [],
            "total_unmatched": len(statement_lines),
            "total_pending": len(manual_transactions),
        }

    # Run matching engine
    match_results = find_matches(
        statement_lines=list(statement_lines),
        manual_transactions=list(manual_transactions),
    )

    suggestions = match_results.get("suggestions", [])[:limit]
    auto_matches = match_results.get("auto_matches", [])[:limit]

    # Convert to schema format
    from app.services.auto_matcher import MatchType

    suggestion_responses = [
        {
            "score": m.score,
            "statement_id": m.statement_id,
            "transaction_id": m.transaction_manual_id,
            "match_type": m.match_type.value,
            "breakdown": m.breakdown,
        }
        for m in suggestions
    ]

    auto_match_responses = [
        {
            "score": m.score,
            "statement_id": m.statement_id,
            "transaction_id": m.transaction_manual_id,
            "match_type": m.match_type.value,
            "breakdown": m.breakdown,
        }
        for m in auto_matches
    ]

    return {
        "suggestions": suggestion_responses,
        "auto_matches": auto_match_responses,
        "total_unmatched": len(statement_lines),
        "total_pending": len(manual_transactions),
    }
