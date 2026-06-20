"""
Auto-matching engine for bank statement lines and manual transactions.

Implements the exact algorithm:
- Same account_id: +40 points (mandatory prerequisite)
- Same amount: +40 points (strict Decimal equality)
- Temporal proximity: +20 if same day, -5 per day (max 3 days window)

Thresholds:
- score >= 80  -> AUTO match
- 50 <= score < 80  -> SUGGESTION
- score < 50  -> NONE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankStatement, StatementStatus
from app.models.transaction import TransactionManual, TransactionStatus
from app.models.conciliation import ConciliationLog

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Match classification
# ---------------------------------------------------------------------------

class MatchType(str, Enum):
    AUTO = "AUTO"
    SUGGESTION = "SUGGESTION"
    NONE = "NONE"


# ---------------------------------------------------------------------------
# Score configuration (exact algorithm constants)
# ---------------------------------------------------------------------------

_ACCOUNT_MATCH_SCORE: Final[int] = 40
_AMOUNT_MATCH_SCORE: Final[int] = 40
_TEMPORAL_MAX_SCORE: Final[int] = 20
_TEMPORAL_DAILY_PENALTY: Final[int] = 5
_TEMPORAL_MAX_DAYS: Final[int] = 3  # window beyond which score is 0

# Thresholds
_AUTO_THRESHOLD: Final[int] = 80
_SUGGESTION_THRESHOLD: Final[int] = 50


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MatchScore:
    """
    Immutable result of scoring one statement line against one manual transaction.
    """
    statement_id: str
    transaction_manual_id: str
    score: int
    match_type: MatchType
    breakdown: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

def _days_between(a: date, b: date) -> int:
    """Return the absolute number of days between two dates."""
    return abs((a - b).days)


def calculate_match_score(statement_line: BankStatement, manual_tx: TransactionManual) -> int:
    """
    Calculate a match score (0-100) between a bank statement line and a manual transaction.

    Rules:
        - Same account_id: +40 points (mandatory; if different, score = 0 immediately)
        - Same amount: +40 points (strict Decimal equality)
        - Temporal proximity:
            - +20 if same day
            - -5 per day of difference
            - max(0, 20 - (days_difference * 5))
            - Zero if more than 3 days apart.

    Args:
        statement_line: A ``BankStatement`` row.
        manual_tx: A ``TransactionManual`` row.

    Returns:
        Integer score in range [0, 100].
    """
    score = 0
    breakdown: dict[str, int] = {}

    # 1. Account match (mandatory prerequisite)
    if statement_line.account_id != manual_tx.account_id:
        return 0
    score += _ACCOUNT_MATCH_SCORE
    breakdown["account"] = _ACCOUNT_MATCH_SCORE

    # 2. Amount match (strict Decimal equality)
    if statement_line.amount == manual_tx.amount:
        score += _AMOUNT_MATCH_SCORE
        breakdown["amount"] = _AMOUNT_MATCH_SCORE
    else:
        breakdown["amount"] = 0

    # 3. Temporal proximity
    days_diff = _days_between(statement_line.date, manual_tx.date)
    if days_diff > _TEMPORAL_MAX_DAYS:
        temporal_score = 0
    else:
        temporal_score = max(0, _TEMPORAL_MAX_SCORE - (days_diff * _TEMPORAL_DAILY_PENALTY))

    score += temporal_score
    breakdown["temporal"] = temporal_score

    return score


def _classify(score: int) -> MatchType:
    """Classify a numeric score into AUTO / SUGGESTION / NONE."""
    if score >= _AUTO_THRESHOLD:
        return MatchType.AUTO
    if score >= _SUGGESTION_THRESHOLD:
        return MatchType.SUGGESTION
    return MatchType.NONE


# ---------------------------------------------------------------------------
# Batch matching
# ---------------------------------------------------------------------------

def find_matches(
    statement_lines: list[BankStatement],
    manual_transactions: list[TransactionManual],
    auto_threshold: int = _AUTO_THRESHOLD,
    suggestion_threshold: int = _SUGGESTION_THRESHOLD,
) -> dict[str, list[MatchScore]]:
    """
    For each statement line, evaluate every manual transaction and classify
    the result as AUTO, SUGGESTION, or NONE.

    Args:
        statement_lines: List of ``BankStatement`` objects to match.
        manual_transactions: List of ``TransactionManual`` objects (candidates).
        auto_threshold: Minimum score for an AUTO match (default 80).
        suggestion_threshold: Minimum score for a SUGGESTION (default 50).

    Returns:
        dict with keys ``auto_matches``, ``suggestions``, ``unmatched``.
        Each value is a list of ``MatchScore`` objects sorted descending by score.
    """
    # Allow runtime override of thresholds
    def classify_dynamic(score: int) -> MatchType:
        if score >= auto_threshold:
            return MatchType.AUTO
        if score >= suggestion_threshold:
            return MatchType.SUGGESTION
        return MatchType.NONE

    auto_matches: list[MatchScore] = []
    suggestions: list[MatchScore] = []
    unmatched: list[MatchScore] = []

    for stmt in statement_lines:
        for tx in manual_transactions:
            raw_score = calculate_match_score(stmt, tx)
            mtype = classify_dynamic(raw_score)
            breakdown = {
                "account": _ACCOUNT_MATCH_SCORE if stmt.account_id == tx.account_id else 0,
                "amount": _AMOUNT_MATCH_SCORE if stmt.amount == tx.amount else 0,
                "temporal": max(
                    0,
                    _TEMPORAL_MAX_SCORE
                    - (_days_between(stmt.date, tx.date) * _TEMPORAL_DAILY_PENALTY),
                ),
            }

            match = MatchScore(
                statement_id=str(stmt.id),
                transaction_manual_id=str(tx.id),
                score=raw_score,
                match_type=mtype,
                breakdown=breakdown,
            )

            if mtype == MatchType.AUTO:
                auto_matches.append(match)
            elif mtype == MatchType.SUGGESTION:
                suggestions.append(match)
            else:
                unmatched.append(match)

    # Sort each bucket by descending score for deterministic ordering
    auto_matches.sort(key=lambda m: m.score, reverse=True)
    suggestions.sort(key=lambda m: m.score, reverse=True)
    unmatched.sort(key=lambda m: m.score, reverse=True)

    return {
        "auto_matches": auto_matches,
        "suggestions": suggestions,
        "unmatched": unmatched,
    }


# ---------------------------------------------------------------------------
# ACID application of auto-matches
# ---------------------------------------------------------------------------

async def apply_auto_matches(
    matches: list[MatchScore],
    db_session: AsyncSession,
) -> list[ConciliationLog]:
    """
    Apply all auto-matches within a single ACID transaction.

    For each ``MatchScore`` of type ``AUTO``:
        1. Insert a ``ConciliationLog`` entry.
        2. Update ``transactions_manual.status`` to ``'CONCILED'``.
        3. Update ``bank_statements.status`` to ``'MATCHED'``.

    If **any** operation fails, the entire transaction is rolled back and
    an exception is raised.

    Args:
        matches: List of ``MatchScore`` objects (typically the
                 ``auto_matches`` bucket from :func:`find_matches`).
        db_session: An active SQLAlchemy 2.0 ``AsyncSession``.

    Returns:
        List of created ``ConciliationLog`` ORM instances (not yet committed
        if the caller manages the transaction boundary).
    """
    created_logs: list[ConciliationLog] = []

    try:
        for match in matches:
            if match.match_type != MatchType.AUTO:
                continue

            # Resolve family_id from statement side
            stmt_result = await db_session.execute(
                select(BankStatement.family_id).where(
                    BankStatement.id == match.statement_id
                )
            )
            family_id_row = stmt_result.scalar_one_or_none()
            if family_id_row is None:
                raise RuntimeError(
                    f"BankStatement {match.statement_id} not found during auto-match application."
                )
            family_id = str(family_id_row)

            # 1. Create conciliation log entry
            log = ConciliationLog(
                family_id=family_id,
                transaction_manual_id=match.transaction_manual_id,
                bank_statement_id=match.statement_id,
                conciliated_by=None,  # system-generated
            )
            db_session.add(log)
            created_logs.append(log)

            # 2. Update manual transaction status -> CONCILED
            await db_session.execute(
                update(TransactionManual)
                .where(TransactionManual.id == match.transaction_manual_id)
                .values(status=TransactionStatus.CONCILED.value)
            )

            # 3. Update bank statement status -> MATCHED
            await db_session.execute(
                update(BankStatement)
                .where(BankStatement.id == match.statement_id)
                .values(status=StatementStatus.MATCHED.value)
            )

        await db_session.commit()
        return created_logs

    except Exception:
        await db_session.rollback()
        raise
