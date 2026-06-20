"""
Transactions router for Orbita.

Provides CRUD endpoints for manual transactions and receipt image
upload/retrieval. All endpoints are scoped to the current user's family
(multi-tenant).
"""
from datetime import date, datetime, timezone
from typing import List
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.transaction import TransactionManual, TransactionStatus
from app.models.user import User
from app.schemas import (
    ReceiptUploadResponse,
    TransactionCreate,
    TransactionListFilter,
    TransactionRead,
    TransactionUpdate,
)
from app.services import (
    ImageProcessingError,
    ImageValidationError,
    process_receipt_image,
    validate_image_mime,
)

router = APIRouter(prefix="/transactions", tags=["Transactions"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_transaction_or_404(
    db: AsyncSession,
    transaction_id: UUID,
    family_id: UUID,
) -> TransactionManual:
    """Fetch a transaction by ID ensuring it belongs to the given family."""
    result = await db.execute(
        select(TransactionManual).where(
            TransactionManual.id == transaction_id,
            TransactionManual.family_id == family_id,
            TransactionManual.deleted_at.is_(None),
        )
    )
    transaction = result.scalar_one_or_none()
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    return transaction


# ---------------------------------------------------------------------------
# Transaction CRUD
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[TransactionRead])
async def list_transactions(
    account_id: UUID | None = Query(None, description="Filter by bank account ID"),
    category_id: UUID | None = Query(None, description="Filter by budget category ID"),
    status_filter: TransactionStatus | None = Query(
        None, alias="status", description="Filter by transaction status"
    ),
    date_from: date | None = Query(None, description="Filter from date (inclusive)"),
    date_to: date | None = Query(None, description="Filter to date (inclusive)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List manual transactions for the current user's family.

    Supports filtering by account, category, status, and date range.
    """
    query = select(TransactionManual).where(
        TransactionManual.family_id == current_user.family_id,
        TransactionManual.deleted_at.is_(None),
    )

    if account_id is not None:
        query = query.where(TransactionManual.account_id == account_id)
    if category_id is not None:
        query = query.where(TransactionManual.category_id == category_id)
    if status_filter is not None:
        query = query.where(TransactionManual.status == status_filter.value)
    if date_from is not None:
        query = query.where(TransactionManual.date >= date_from)
    if date_to is not None:
        query = query.where(TransactionManual.date <= date_to)

    result = await db.execute(query)
    transactions = result.scalars().all()
    return transactions


@router.post(
    "/",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    body: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new manual transaction.

    The ``user_id`` is automatically set to the current authenticated user.
    """
    transaction = TransactionManual(
        family_id=current_user.family_id,
        user_id=current_user.id,
        account_id=body.account_id,
        category_id=body.category_id,
        amount=body.amount,
        date=body.date,
        description=body.description,
        status=TransactionStatus.PENDING.value,
    )
    db.add(transaction)
    await db.flush()
    await db.refresh(transaction)
    return transaction


@router.get("/{transaction_id}", response_model=TransactionRead)
async def get_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single transaction by ID (family-scoped)."""
    transaction = await _get_transaction_or_404(
        db, transaction_id, current_user.family_id
    )
    return transaction


@router.put("/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: UUID,
    body: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a manual transaction. Only provided fields are updated."""
    transaction = await _get_transaction_or_404(
        db, transaction_id, current_user.family_id
    )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        # Handle enum values
        if hasattr(value, "value"):
            setattr(transaction, field, value.value)
        else:
            setattr(transaction, field, value)

    return transaction


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft delete a manual transaction."""
    transaction = await _get_transaction_or_404(
        db, transaction_id, current_user.family_id
    )
    transaction.soft_delete()
    return None


# ---------------------------------------------------------------------------
# Receipt handling
# ---------------------------------------------------------------------------

@router.post(
    "/{transaction_id}/receipt",
    response_model=ReceiptUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_receipt(
    transaction_id: UUID,
    file: UploadFile = File(..., description="Receipt image (JPEG, PNG, or WebP)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload a receipt image for a transaction.

    The image is validated, resized, transcoded to WebP, and uploaded to S3.
    The transaction's ``receipt_url`` is updated with the S3 key.
    """
    transaction = await _get_transaction_or_404(
        db, transaction_id, current_user.family_id
    )

    # Read uploaded file bytes
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded",
        )

    # Validate and process the image
    try:
        s3_key = process_receipt_image(
            file_bytes=file_bytes,
            family_id=str(current_user.family_id),
            transaction_id=str(transaction_id),
            year=transaction.date.year,
        )
    except ImageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ImageProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image processing failed: {exc}",
        ) from exc

    # Update transaction with receipt URL
    transaction.receipt_url = s3_key

    return ReceiptUploadResponse(
        transaction_id=transaction_id,
        receipt_url=s3_key,
        message="Receipt uploaded successfully",
    )


@router.get("/{transaction_id}/receipt")
async def get_receipt(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get the receipt S3 URL for a transaction.

    Returns the S3 key stored in ``receipt_url``. The frontend can use this
    to generate a presigned URL or directly access the image if the bucket
    is public.
    """
    transaction = await _get_transaction_or_404(
        db, transaction_id, current_user.family_id
    )

    if not transaction.receipt_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No receipt found for this transaction",
        )

    return {
        "transaction_id": transaction_id,
        "receipt_url": transaction.receipt_url,
    }
