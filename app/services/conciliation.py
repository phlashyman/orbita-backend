"""
Manual conciliation workflow service.

Provides ACID-safe operations for:
- Creating manual matches between statement lines and manual transactions.
- Undoing (unmatching) previous conciliations.
- Assigning unmatched statement lines to family members for clarification.
- Reporting reconciliation status summaries.
"""

from __future__ import annotations

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankStatement, StatementStatus
from app.models.transaction import TransactionManual, TransactionStatus
from app.models.conciliation import ConciliationLog


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ConciliationError(RuntimeError):
    """Raised when a conciliation operation fails and the transaction is rolled back."""


class NotFoundError(ValueError):
    """Raised when a referenced entity does not exist."""


# ---------------------------------------------------------------------------
# Manual match creation
# ---------------------------------------------------------------------------

async def create_manual_match(
    db: AsyncSession,
    family_id: str,
    transaction_manual_id: str,
    bank_statement_id: str,
    conciliated_by: str,
) -> ConciliationLog:
    """
    Create a manual match within an ACID transaction.

    Steps:
        1. Insert into ``conciliations_log``.
        2. Update ``transactions_manual.status`` to ``'CONCILED'``.
        3. Update ``bank_statements.status`` to ``'MATCHED'``.
        4. Commit all or rollback on any failure.

    Args:
        db: Active async SQLAlchemy session.
        family_id: UUID string of the family.
        transaction_manual_id: UUID string of the manual transaction.
        bank_statement_id: UUID string of the bank statement line.
        conciliated_by: UUID string of the user performing the match.

    Returns:
        The newly created ``ConciliationLog`` instance.

    Raises:
        NotFoundError: If either the manual transaction or statement line is missing.
        ConciliationError: On any database failure (transaction rolled back).
    """
    try:
        # Verify both entities exist and belong to the same family
        tx_result = await db.execute(
            select(TransactionManual).where(
                TransactionManual.id == transaction_manual_id,
                TransactionManual.family_id == family_id,
            )
        )
        tx = tx_result.scalar_one_or_none()
        if tx is None:
            raise NotFoundError(
                f"TransactionManual {transaction_manual_id} not found for family {family_id}."
            )

        stmt_result = await db.execute(
            select(BankStatement).where(
                BankStatement.id == bank_statement_id,
                BankStatement.family_id == family_id,
            )
        )
        stmt = stmt_result.scalar_one_or_none()
        if stmt is None:
            raise NotFoundError(
                f"BankStatement {bank_statement_id} not found for family {family_id}."
            )

        # 1. Insert conciliation log
        log = ConciliationLog(
            family_id=family_id,
            transaction_manual_id=transaction_manual_id,
            bank_statement_id=bank_statement_id,
            conciliated_by=conciliated_by,
        )
        db.add(log)
        await db.flush()  # flush to generate log.id before commit

        # 2. Update manual transaction status
        await db.execute(
            update(TransactionManual)
            .where(TransactionManual.id == transaction_manual_id)
            .values(status=TransactionStatus.CONCILED.value)
        )

        # 3. Update bank statement status
        await db.execute(
            update(BankStatement)
            .where(BankStatement.id == bank_statement_id)
            .values(status=StatementStatus.MATCHED.value)
        )

        await db.commit()
        return log

    except NotFoundError:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        raise ConciliationError(
            f"Manual match creation failed: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Unmatch (undo a conciliation)
# ---------------------------------------------------------------------------

async def unmatch(
    db: AsyncSession,
    conciliation_log_id: str,
) -> None:
    """
    Undo a match within an ACID transaction.

    Steps:
        1. Resolve the conciliation log entry.
        2. Revert ``transactions_manual.status`` to ``'PENDING'``.
        3. Revert ``bank_statements.status`` to ``'UNMATCHED'``.
        4. Delete the conciliation log row.
        5. Commit all or rollback on any failure.

    Args:
        db: Active async SQLAlchemy session.
        conciliation_log_id: UUID string of the conciliation log to undo.

    Raises:
        NotFoundError: If the conciliation log entry does not exist.
        ConciliationError: On any database failure (transaction rolled back).
    """
    try:
        # Resolve the log entry to get referenced IDs
        result = await db.execute(
            select(ConciliationLog).where(ConciliationLog.id == conciliation_log_id)
        )
        log = result.scalar_one_or_none()
        if log is None:
            raise NotFoundError(
                f"ConciliationLog {conciliation_log_id} not found."
            )

        transaction_manual_id = log.transaction_manual_id
        bank_statement_id = log.bank_statement_id

        # 1. Revert manual transaction status -> PENDING
        await db.execute(
            update(TransactionManual)
            .where(TransactionManual.id == transaction_manual_id)
            .values(status=TransactionStatus.PENDING.value)
        )

        # 2. Revert bank statement status -> UNMATCHED
        await db.execute(
            update(BankStatement)
            .where(BankStatement.id == bank_statement_id)
            .values(status=StatementStatus.UNMATCHED.value)
        )

        # 3. Delete the conciliation log
        await db.execute(
            delete(ConciliationLog).where(
                ConciliationLog.id == conciliation_log_id
            )
        )

        await db.commit()

    except NotFoundError:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        raise ConciliationError(
            f"Unmatch operation failed: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Assignment to family member
# ---------------------------------------------------------------------------

async def assign_statement_to_user(
    db: AsyncSession,
    statement_id: str,
    user_id: str,
) -> BankStatement:
    """
    Assign an unmatched bank statement line to a family member for clarification.

    Updates the statement's status to ``RECONCILIATION_REQUIRED`` and sets
    ``assigned_user_id`` to the given user.

    Args:
        db: Active async SQLAlchemy session.
        statement_id: UUID string of the bank statement line.
        user_id: UUID string of the user to assign.

    Returns:
        The updated ``BankStatement`` instance.

    Raises:
        NotFoundError: If the statement line does not exist.
        ConciliationError: On any database failure (transaction rolled back).
    """
    try:
        result = await db.execute(
            select(BankStatement).where(BankStatement.id == statement_id)
        )
        stmt = result.scalar_one_or_none()
        if stmt is None:
            raise NotFoundError(
                f"BankStatement {statement_id} not found."
            )

        stmt.status = StatementStatus.RECONCILIATION_REQUIRED.value
        stmt.assigned_user_id = user_id

        await db.commit()
        await db.refresh(stmt)
        return stmt

    except NotFoundError:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        raise ConciliationError(
            f"Assignment to user failed: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Reconciliation status summary
# ---------------------------------------------------------------------------

async def get_reconciliation_status(
    db: AsyncSession,
    family_id: str,
    account_id: str | None = None,
) -> dict:
    """
    Return a summary of reconciliation state for a family (optionally filtered
    by a single bank account).

    Args:
        db: Active async SQLAlchemy session.
        family_id: UUID string of the family.
        account_id: Optional UUID string of a specific bank account.

    Returns:
        dict with the following keys:
            - total_manual_transactions (int)
            - total_statement_lines (int)
            - matched (int)
            - unmatched_manual (int)
            - unmatched_statements (int)
            - reconciliation_required (int)
            - suggestions_pending (int) — currently 0; reserved for future use
    """
    # Build base filters
    tx_filter = [TransactionManual.family_id == family_id]
    stmt_filter = [BankStatement.family_id == family_id]

    if account_id is not None:
        tx_filter.append(TransactionManual.account_id == account_id)
        stmt_filter.append(BankStatement.account_id == account_id)

    # Count manual transactions
    total_manual_result = await db.execute(
        select(func.count()).select_from(TransactionManual).where(*tx_filter)
    )
    total_manual_transactions = total_manual_result.scalar() or 0

    # Count unmatched manual transactions (status == PENDING)
    unmatched_manual_result = await db.execute(
        select(func.count())
        .select_from(TransactionManual)
        .where(
            *tx_filter,
            TransactionManual.status == TransactionStatus.PENDING.value,
        )
    )
    unmatched_manual = unmatched_manual_result.scalar() or 0

    # Count total statement lines
    total_stmt_result = await db.execute(
        select(func.count()).select_from(BankStatement).where(*stmt_filter)
    )
    total_statement_lines = total_stmt_result.scalar() or 0

    # Count matched statements
    matched_result = await db.execute(
        select(func.count())
        .select_from(BankStatement)
        .where(
            *stmt_filter,
            BankStatement.status == StatementStatus.MATCHED.value,
        )
    )
    matched = matched_result.scalar() or 0

    # Count unmatched statements
    unmatched_stmt_result = await db.execute(
        select(func.count())
        .select_from(BankStatement)
        .where(
            *stmt_filter,
            BankStatement.status == StatementStatus.UNMATCHED.value,
        )
    )
    unmatched_statements = unmatched_stmt_result.scalar() or 0

    # Count reconciliation-required statements
    recon_required_result = await db.execute(
        select(func.count())
        .select_from(BankStatement)
        .where(
            *stmt_filter,
            BankStatement.status == StatementStatus.RECONCILIATION_REQUIRED.value,
        )
    )
    reconciliation_required = recon_required_result.scalar() or 0

    return {
        "total_manual_transactions": total_manual_transactions,
        "total_statement_lines": total_statement_lines,
        "matched": matched,
        "unmatched_manual": unmatched_manual,
        "unmatched_statements": unmatched_statements,
        "reconciliation_required": reconciliation_required,
        "suggestions_pending": 0,  # placeholder for future suggestion pipeline
    }
