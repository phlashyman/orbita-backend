"""
Orbita business-logic services package.

All service modules expose their public API here for clean imports:

    from app.services import (
        process_receipt_image,
        validate_image_mime,
        calculate_match_score,
        find_matches,
        apply_auto_matches,
        create_manual_match,
        unmatch,
        assign_statement_to_user,
        get_reconciliation_status,
    )
"""

# Receipt pipeline
from app.services.receipt_pipeline import (
    process_receipt_image,
    validate_image_mime,
    ImageValidationError,
    ImageProcessingError,
)

# Auto-matching engine
from app.services.auto_matcher import (
    calculate_match_score,
    find_matches,
    apply_auto_matches,
    MatchScore,
    MatchType,
)

# Manual conciliation workflow
from app.services.conciliation import (
    create_manual_match,
    unmatch,
    assign_statement_to_user,
    get_reconciliation_status,
    ConciliationError,
    NotFoundError,
)

__all__ = [
    # Receipt pipeline
    "process_receipt_image",
    "validate_image_mime",
    "ImageValidationError",
    "ImageProcessingError",
    # Auto-matcher
    "calculate_match_score",
    "find_matches",
    "apply_auto_matches",
    "MatchScore",
    "MatchType",
    # Conciliation
    "create_manual_match",
    "unmatch",
    "assign_statement_to_user",
    "get_reconciliation_status",
    "ConciliationError",
    "NotFoundError",
]
