"""
Broker File Upload router for Orbita.

Provides endpoints for uploading broker portfolio statement files (CSV, XLSX,
PDF, TXT), parsing them to extract positions, and importing those positions as
portfolio holdings.

INTEGRATION: orbita_ingest parsers (v2)
  - Uses scoring-based file detection (detect.py)
  - Supports 8 file types: aurea_carteira, aurea_destaques, standard_carteira,
    ordens_disponiveis, bodiva_resumo, bodiva_boletim, bodiva_relatorio,
    ficha_tecnica
  - Idempotency: SHA-256 hash check in import_log (skip if already imported)
  - Admin-only: BODIVA institutional files require admin role
  - Atomic: DB transaction per upload (rollback on error)

All endpoints are scoped to the current user's family (multi-tenant).
"""
from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.broker import Broker
from app.models.broker_file_upload import BrokerFileUpload
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio
from app.models.portfolio_holding import PortfolioHolding
from app.models.trade import Trade
from app.models.user import User
from app.schemas import (
    BrokerFileImportRequest,
    BrokerFileImportResult,
    BrokerFileProcessResult,
    BrokerFileUploadListItem,
    BrokerFileUploadRead,
    BrokerFileUploadUpdate,
    BrokerPositionExtracted,
    PortfolioHoldingRead,
)
from app.utils.s3 import get_s3_client
from app.config import settings

# ---------------------------------------------------------------------------
# orbita_ingest integration
# ---------------------------------------------------------------------------
from app.services.ingestion.service import (
    parse_file,
    detect_only,
    UndetectedFile,
    ForbiddenFile,
)
from app.services.ingestion.common import IngestResult, sha256_of_bytes
from app.services.ingestion.persistence_sqlalchemy import apply_ingest_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio/uploads", tags=["Broker File Uploads"])

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_ALLOWED_EXTENSIONS: set[str] = {"csv", "xlsx", "xls", "pdf", "txt"}

# Ficheiros institucionais BODIVA -> so ADMIN pode carregar
ADMIN_ONLY_PARSERS = {
    "bodiva_resumo", "bodiva_resumo_mercados",
    "bodiva_boletim", "bodiva_boletim_oficial",
    "bodiva_relatorio_mensal", "bodiva_relatorio_trimestral",
}

# Diretorio temporario para ficheiros (Render: /app/broker-files/, local: /tmp/)
TEMP_DIR = os.environ.get("BROKER_FILES_DIR", "/tmp/orbita-uploads")

# Mapeia o parser detectado (ficheiro do broker) para o broker correspondente.
# Permite criar/seleccionar automaticamente o broker sem o utilizador ter de o
# cadastrar manualmente via POST /portfolio/brokers antes do upload.
PARSER_BROKER_MAP: dict[str, tuple[str, str]] = {
    "aurea_carteira": ("AUREA", "Aurea Corretora"),
    "aurea_destaques": ("AUREA", "Aurea Corretora"),
    "standard_carteira": ("STANDARD", "Standard Gestão de Activos"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_upload_or_404(
    db: AsyncSession,
    upload_id: UUID,
    family_id: UUID,
) -> BrokerFileUpload:
    """Fetch an upload by ID ensuring it belongs to the given family."""
    result = await db.execute(
        select(BrokerFileUpload).where(
            BrokerFileUpload.id == upload_id,
            BrokerFileUpload.family_id == family_id,
            BrokerFileUpload.deleted_at.is_(None),
        )
    )
    upload = result.scalar_one_or_none()
    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )
    return upload


async def _get_or_create_broker(db: AsyncSession, code: str, name: str) -> Broker:
    """Find a broker by its internal code, creating it if it does not exist yet."""
    result = await db.execute(select(Broker).where(Broker.code == code))
    broker = result.scalar_one_or_none()
    if broker is None:
        broker = Broker(name=name, code=code, is_active=True)
        db.add(broker)
        await db.flush()
        await db.refresh(broker)
    return broker


async def _detect_broker(
    db: AsyncSession, upload: BrokerFileUpload, parser_key: Optional[str]
) -> Optional[Broker]:
    """
    Auto-detect the broker from the file type and, if the upload doesn't
    already have one assigned, associate it automatically.
    """
    mapping = PARSER_BROKER_MAP.get(parser_key or "")
    if mapping is None:
        return None
    code, name = mapping
    broker = await _get_or_create_broker(db, code, name)
    if upload.broker_id is None:
        upload.broker_id = broker.id
        await db.flush()
    return broker


def _generate_s3_key(family_id: UUID, stored_filename: str) -> str:
    """Generate S3 key: broker-files/{family_id}/{year}/{stored_filename}"""
    year = datetime.now().year
    return f"broker-files/{family_id}/{year}/{stored_filename}"


def _validate_extension(filename: str) -> str:
    """
    Validate file extension and return the lower-case extension.
    Raises HTTPException 422 if the extension is not allowed.
    """
    if "." not in filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File has no extension. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}",
        )
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid file extension '.{ext}'. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}",
        )
    return ext


def _positions_to_schema(
    positions: List[BrokerPositionExtracted],
) -> List[BrokerPositionExtracted]:
    """Pass-through: already schema objects."""
    return positions


def _file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _read_upload_file(upload: BrokerFileUpload) -> bytes:
    """Read file bytes from local storage or S3."""
    if upload.s3_key.startswith("local://"):
        local_path = upload.s3_key.replace("local://", "")
        return Path(local_path).read_bytes()
    else:
        s3 = get_s3_client()
        response = s3.get_object(Bucket=settings.s3_bucket, Key=upload.s3_key)
        return response["Body"].read()


def _save_temp_file(file_bytes: bytes, filename: str) -> str:
    """Save bytes to a temporary file and return the path."""
    os.makedirs(TEMP_DIR, exist_ok=True)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "tmp"
    tmp_path = os.path.join(TEMP_DIR, f"{uuid4().hex}.{ext}")
    with open(tmp_path, "wb") as f:
        f.write(file_bytes)
    return tmp_path


def _safe_float(value: Any) -> Optional[float]:
    """Safely convert a value to float, returning None if not possible."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ingest_result_to_positions(result: IngestResult) -> List[BrokerPositionExtracted]:
    """Convert IngestResult DBRows to BrokerPositionExtracted schema."""
    snapshot_tickers = {
        row.values.get("ticker")
        for row in result.rows
        if row.table == "portfolio_snapshots"
    }

    positions = []
    for row in result.rows:
        v = row.values
        # Only include rows from portfolio_snapshots (carteira holdings)
        if row.table == "portfolio_snapshots":
            # Convert to float for schema compatibility
            qty = _safe_float(v.get("quantity_total"))
            price = _safe_float(v.get("quote_price"))
            val = _safe_float(v.get("current_value_aoa"))
            positions.append(BrokerPositionExtracted(
                ticker=v.get("ticker", ""),
                name=v.get("title") or v.get("name", ""),
                quantity=qty,
                price=price,
                value=val,
                instrument_type=v.get("instrument_class") or "",
                market=v.get("market"),
                currency=v.get("currency"),
                par_value=_safe_float(v.get("par_value_unit")),
                acquisition_value=_safe_float(v.get("acquisition_value")),
                unrealized_pnl=_safe_float(v.get("unrealized_pnl")),
                unrealized_pnl_pct=_safe_float(v.get("unrealized_pnl_pct")),
                daily_variation_pct=_safe_float(v.get("daily_variation_pct")),
                weight_pct=_safe_float(v.get("weight_pct")),
                raw_data=v,
            ))
        # For bond_master rows (ficha tecnica), show as position with ISIN info
        # -- but skip if a portfolio_snapshots row for the same ticker already
        # exists, since that one carries the actual holding data and this
        # entry would just be a duplicate with empty quantity/price/value.
        elif row.table == "bond_master":
            if v.get("ticker") in snapshot_tickers:
                continue
            positions.append(BrokerPositionExtracted(
                ticker=v.get("ticker", ""),
                name=v.get("title", ""),
                quantity=None,
                price=None,
                value=None,
                instrument_type=v.get("instrument_class", ""),
                raw_data=v,
            ))
        # For market_snapshots (destaques, boletim), include as price data
        elif row.table == "market_snapshots":
            positions.append(BrokerPositionExtracted(
                ticker=v.get("ticker", ""),
                name=v.get("ticker", ""),
                quantity=_safe_float(v.get("volume_qty")),
                price=_safe_float(v.get("price")),
                value=_safe_float(v.get("volume_aoa")),
                instrument_type=v.get("instrument_class", ""),
                raw_data=v,
            ))
    return positions


def _coerce_for_db(value: Any) -> Any:
    """Coerce ISO date strings to Python date/datetime for asyncpg/SQLAlchemy."""
    if isinstance(value, str) and len(value) == 10 and value[4] == "-" and value[7] == "-":
        try:
            return date.fromisoformat(value)
        except ValueError:
            return value
    return value


def _make_json_safe(obj: Any) -> Any:
    """Recursively convert Decimal to float for PostgreSQL JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_safe(i) for i in obj]
    return obj


# ---------------------------------------------------------------------------
# Upload endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=BrokerFileUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_broker_file(
    file: UploadFile = File(..., description="Broker statement file (CSV, XLSX, PDF, or TXT)"),
    broker_id: Optional[UUID] = Form(None, description="Optional broker association"),
    portfolio_id: Optional[UUID] = Form(None, description="Optional target portfolio"),
    notes: Optional[str] = Form(None, description="User notes"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Upload a broker portfolio statement file.

    The file is stored (S3 or local) under ``broker-files/{family_id}/{year}/``
    and a database record is created with status ``PENDING``.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No filename provided",
        )

    # Validate extension
    ext = _validate_extension(file.filename)

    # Read file content
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded",
        )

    file_size = len(file_bytes)

    # Generate UUID-based filename
    stored_filename = f"{uuid4()}.{ext}"

    # Try S3 first, fallback to local storage
    s3_key = None
    try:
        s3 = get_s3_client()
        s3_key = _generate_s3_key(current_user.family_id, stored_filename)
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=s3_key,
            Body=file_bytes,
            ContentType=_get_content_type(ext),
        )
    except Exception as s3_exc:
        logger.warning("S3 upload failed, using local storage: %s", s3_exc)
        local_dir = os.path.join(TEMP_DIR, str(current_user.family_id), str(datetime.now().year))
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, stored_filename)
        with open(local_path, "wb") as f:
            f.write(file_bytes)
        s3_key = f"local://{local_path}"

    # Create database record
    upload = BrokerFileUpload(
        family_id=current_user.family_id,
        user_id=current_user.id,
        broker_id=broker_id,
        portfolio_id=portfolio_id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        s3_key=s3_key,
        file_size=file_size,
        file_type=ext.upper(),
        status="PENDING",
        notes=notes,
    )
    db.add(upload)
    await db.flush()
    await db.refresh(upload)

    return BrokerFileUploadRead(
        id=upload.id,
        family_id=upload.family_id,
        user_id=upload.user_id,
        broker_id=upload.broker_id,
        portfolio_id=upload.portfolio_id,
        original_filename=upload.original_filename,
        stored_filename=upload.stored_filename,
        s3_key=upload.s3_key,
        file_size=upload.file_size,
        file_type=upload.file_type,
        status=upload.status,
        parsed_data=None,
        error_message=upload.error_message,
        notes=upload.notes,
        created_at=upload.created_at,
        updated_at=upload.updated_at,
    )


@router.get("", response_model=List[BrokerFileUploadListItem])
async def list_uploads(
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    List broker file uploads for the current user's family.
    Optionally filter by status (PENDING, PROCESSING, PROCESSED, ERROR, SKIPPED).
    """
    query = select(BrokerFileUpload).where(
        BrokerFileUpload.family_id == current_user.family_id,
        BrokerFileUpload.deleted_at.is_(None),
    )

    if status_filter:
        query = query.where(BrokerFileUpload.status == status_filter.upper())

    query = query.order_by(BrokerFileUpload.created_at.desc())
    result = await db.execute(query)
    uploads = result.scalars().all()

    return [
        BrokerFileUploadListItem(
            id=u.id,
            family_id=u.family_id,
            user_id=u.user_id,
            broker_id=u.broker_id,
            portfolio_id=u.portfolio_id,
            original_filename=u.original_filename,
            file_type=u.file_type,
            file_size=u.file_size,
            status=u.status,
            notes=u.notes,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )
        for u in uploads
    ]


@router.get("/{upload_id}", response_model=BrokerFileUploadRead)
async def get_upload(
    upload_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single upload by ID with full details including parsed positions."""
    upload = await _get_upload_or_404(db, upload_id, current_user.family_id)

    parsed_data = None
    if upload.parsed_data:
        parsed_data = [
            BrokerPositionExtracted(
                ticker=p.get("ticker"),
                name=p.get("name") or p.get("title", ""),
                quantity=_safe_float(p.get("quantity") or p.get("quantity_total")),
                price=_safe_float(p["price"]) if p.get("price") is not None else None,
                value=_safe_float(p["value"]) if p.get("value") is not None else None,
                instrument_type=p.get("instrument_type") or p.get("instrument_class", ""),
                raw_data=p.get("raw_data"),
            )
            for p in upload.parsed_data
        ]

    return BrokerFileUploadRead(
        id=upload.id,
        family_id=upload.family_id,
        user_id=upload.user_id,
        broker_id=upload.broker_id,
        portfolio_id=upload.portfolio_id,
        original_filename=upload.original_filename,
        stored_filename=upload.stored_filename,
        s3_key=upload.s3_key,
        file_size=upload.file_size,
        file_type=upload.file_type,
        status=upload.status,
        parsed_data=parsed_data,
        error_message=upload.error_message,
        notes=upload.notes,
        created_at=upload.created_at,
        updated_at=upload.updated_at,
    )


# ---------------------------------------------------------------------------
# Preview endpoint (NEW - orbita_ingest integration)
# ---------------------------------------------------------------------------

@router.post("/{upload_id}/preview", response_model=BrokerFileProcessResult)
async def preview_upload(
    upload_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Preview file processing WITHOUT writing to the database.

    Detects file type, runs the appropriate parser, and returns extracted
    positions. Use this to verify what will be imported before applying.
    """
    upload = await _get_upload_or_404(db, upload_id, current_user.family_id)

    # Read file bytes
    try:
        file_bytes = await _read_upload_file(upload)
    except Exception as exc:
        return BrokerFileProcessResult(
            upload_id=upload.id,
            status="ERROR",
            file_type=upload.file_type,
            positions_found=0,
            positions=[],
            error_message=f"File read failed: {exc}",
        )

    # Save to temp file (orbita_ingest needs a filesystem path)
    tmp_path = _save_temp_file(file_bytes, upload.original_filename or upload.stored_filename)
    try:
        result = parse_file(
            tmp_path,
            user_id=None,  # preview doesn't need user_id
            is_admin=getattr(current_user, "is_admin", False) or getattr(current_user, "role", "") == "ADMIN",
            portfolio_id=None,
        )

        positions = _ingest_result_to_positions(result)

        # Store preview in parsed_data (not persisted to actual tables)
        upload.parsed_data = [p.model_dump(mode="json") if hasattr(p, "model_dump") else p.dict() for p in positions]
        upload.status = "PREVIEW"
        await db.flush()

        detected_broker = await _detect_broker(db, upload, getattr(result, "detected_key", None))

        return BrokerFileProcessResult(
            upload_id=upload.id,
            status="PREVIEW",
            file_type=upload.file_type,
            positions_found=len(positions),
            positions=positions,
            error_message="; ".join(result.warnings) if result.warnings else None,
            detected_broker_id=detected_broker.id if detected_broker else None,
            detected_broker_name=detected_broker.name if detected_broker else None,
        )

    except UndetectedFile as exc:
        return BrokerFileProcessResult(
            upload_id=upload.id,
            status="UNDETECTED",
            file_type=upload.file_type,
            positions_found=0,
            positions=[],
            error_message=f"File type not recognized: {exc}",
        )
    except ForbiddenFile as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Preview failed for upload %s", upload_id)
        return BrokerFileProcessResult(
            upload_id=upload.id,
            status="ERROR",
            file_type=upload.file_type,
            positions_found=0,
            positions=[],
            error_message=f"Preview failed: {exc}",
        )
    finally:
        # Cleanup temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Process endpoint (INTEGRATED with orbita_ingest)
# ---------------------------------------------------------------------------

@router.post("/{upload_id}/process", response_model=BrokerFileProcessResult)
async def process_upload(
    upload_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Process an uploaded file to extract positions and persist to database.

    Uses orbita_ingest pipeline:
      1. Downloads file from storage (S3 or local).
      2. Saves to temporary filesystem path.
      3. Detects file type and calls appropriate parser.
      4. Checks idempotency (hash in import_log -> skip if already imported).
      5. Applies rows to database (DELETE by natural key + INSERT).
      6. Logs result to import_log.

    BODIVA institutional files require ADMIN role.
    """
    upload = await _get_upload_or_404(db, upload_id, current_user.family_id)

    is_admin = getattr(current_user, "is_admin", False) or getattr(current_user, "role", "") == "ADMIN"

    # Read file bytes
    try:
        file_bytes = await _read_upload_file(upload)
    except Exception as exc:
        upload.status = "ERROR"
        upload.error_message = f"File read failed: {exc}"
        await db.flush()
        return BrokerFileProcessResult(
            upload_id=upload.id,
            status="ERROR",
            file_type=upload.file_type,
            positions_found=0,
            positions=[],
            error_message=f"File read failed: {exc}",
        )

    # Save to temp file (orbita_ingest needs filesystem path)
    tmp_path = _save_temp_file(file_bytes, upload.original_filename or upload.stored_filename)

    upload.status = "PROCESSING"
    await db.flush()

    try:
        # Parse with orbita_ingest
        result = parse_file(
            tmp_path,
            user_id=str(current_user.id),
            is_admin=is_admin,
            portfolio_id=str(upload.portfolio_id) if upload.portfolio_id else None,
        )

        parser_key = getattr(result, "detected_key", "unknown")

        # Check admin-only restriction
        if parser_key in ADMIN_ONLY_PARSERS and not is_admin:
            raise ForbiddenFile(
                f"Ficheiro institucional BODIVA ({parser_key}) - apenas o admin pode carregar."
            )

        # NOTE: Idempotency check disabled - import_log table may not exist
        # TODO: Re-enable after running 004_schema_postgresql.sql
        # hash_exists = False
        # try:
        #     hash_check = await db.execute(
        #         text("SELECT COUNT(*) FROM import_log WHERE file_hash = :h AND status = 'success'"),
        #         {"h": result.file_hash}
        #     )
        #     if hash_check.scalar() > 0:
        #         hash_exists = True
        # except Exception:
        #     pass
        #
        # if hash_exists:
        #     ...skip logic...

        # Apply rows to database (idempotent: DELETE+INSERT by conflict keys)
        persist_out = await apply_ingest_result(db, result)
        applied = persist_out.get("applied", 0)
        warnings_list = list(result.warnings)
        if persist_out.get("status") == "skipped":
            warnings_list.append("Ficheiro já importado anteriormente (idempotência por hash).")
        elif persist_out.get("status") == "failed":
            warnings_list.append(f"Erro na persistência: {persist_out.get('error', '')}")

        # Update upload status
        upload.status = "PROCESSED"
        upload.error_message = None
        positions = _ingest_result_to_positions(result)
        upload.parsed_data = [p.model_dump(mode="json") if hasattr(p, "model_dump") else p.dict() for p in positions]
        await db.flush()

        detected_broker = await _detect_broker(db, upload, parser_key)

        return BrokerFileProcessResult(
            upload_id=upload.id,
            status="PROCESSED",
            file_type=upload.file_type,
            positions_found=len(positions),
            positions=positions,
            error_message="; ".join(warnings_list) if warnings_list else None,
            detected_broker_id=detected_broker.id if detected_broker else None,
            detected_broker_name=detected_broker.name if detected_broker else None,
        )

    except UndetectedFile as exc:
        upload.status = "ERROR"
        upload.error_message = f"File type not recognized: {exc}"
        await db.flush()
        return BrokerFileProcessResult(
            upload_id=upload.id,
            status="UNDETECTED",
            file_type=upload.file_type,
            positions_found=0,
            positions=[],
            error_message=f"File type not recognized. The system could not identify the broker file format. "
                          f"Supported: Aurea Carteira, Aurea Destaques, Standard Carteira, "
                          f"Ordens Disponiveis, BODIVA Resumo, BODIVA Boletim, Ficha Tecnica. "
                          f"Details: {exc}",
        )
    except ForbiddenFile as exc:
        upload.status = "ERROR"
        upload.error_message = str(exc)
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Processing failed for upload %s", upload_id)
        upload.status = "ERROR"
        upload.error_message = str(exc)
        await db.flush()
        return BrokerFileProcessResult(
            upload_id=upload.id,
            status="ERROR",
            file_type=upload.file_type,
            positions_found=0,
            positions=[],
            error_message=f"Processing failed: {exc}",
        )
    finally:
        # Cleanup temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Import endpoint (positions -> holdings + trades)
# ---------------------------------------------------------------------------

@router.post("/{upload_id}/import", response_model=BrokerFileImportResult)
async def import_positions(
    upload_id: UUID,
    body: BrokerFileImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Import extracted positions as portfolio holdings.

    For each position:
    1. Creates a ``PortfolioHolding`` record in the target portfolio.
    2. Creates a ``BUY`` ``Trade`` record to track the transaction.

    Positions without a recognised ticker are still imported with
    ``instrument_id=None`` -- the user can map them later.
    """
    upload = await _get_upload_or_404(db, upload_id, current_user.family_id)

    if upload.status not in ("PROCESSED", "PREVIEW") or not upload.parsed_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload has not been processed or contains no positions. Call /process first.",
        )

    # Resolve target portfolio — verify if provided, else find/create default
    resolved_portfolio_id = body.portfolio_id
    if resolved_portfolio_id is not None:
        portfolio_result = await db.execute(
            select(Portfolio).where(
                Portfolio.id == resolved_portfolio_id,
                Portfolio.family_id == current_user.family_id,
                Portfolio.deleted_at.is_(None),
            )
        )
        if portfolio_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found",
            )
    else:
        # Find the family's default portfolio, or create one automatically
        default_result = await db.execute(
            select(Portfolio).where(
                Portfolio.family_id == current_user.family_id,
                Portfolio.deleted_at.is_(None),
            ).order_by(Portfolio.created_at.asc()).limit(1)
        )
        default_portfolio = default_result.scalar_one_or_none()
        if default_portfolio is None:
            default_portfolio = Portfolio(
                family_id=current_user.family_id,
                user_id=current_user.id,
                name="Carteira Principal",
                portfolio_type="INVESTMENT",
                is_default=True,
            )
            db.add(default_portfolio)
            await db.flush()
            await db.refresh(default_portfolio)
        resolved_portfolio_id = default_portfolio.id

    # Fallback to the broker auto-detected/assigned during preview/process
    # when the request body does not specify one explicitly.
    broker_id = body.broker_id if body.broker_id is not None else upload.broker_id

    # Load all instruments for ticker lookup
    instrument_result = await db.execute(
        select(Instrument).where(Instrument.deleted_at.is_(None))
    )
    instruments = instrument_result.scalars().all()

    # Build ticker -> instrument lookup (case-insensitive)
    ticker_map: dict[str, Instrument] = {}
    for inst in instruments:
        if inst.ticker:
            ticker_map[inst.ticker.upper()] = inst
        if inst.isin:
            ticker_map[inst.isin.upper()] = inst

    holdings_created = 0
    trades_created = 0
    errors: List[str] = []

    for pos in body.positions:
        try:
            # Look up instrument by ticker
            instrument_id = None
            if pos.ticker:
                instrument = ticker_map.get(pos.ticker.upper())
                if instrument:
                    instrument_id = instrument.id

            # Determine quantity and price
            quantity = int(pos.quantity) if pos.quantity else 0
            price = Decimal(str(pos.price)) if pos.price else Decimal("0")
            if price == Decimal("0") and pos.value and quantity and quantity > 0:
                try:
                    price = Decimal(str(pos.value)) / Decimal(str(quantity))
                except Exception:
                    price = Decimal("0")

            total_value = Decimal(str(pos.value)) if pos.value is not None else Decimal(str(quantity)) * price

            # Average buy price: derive from acquisition value when available,
            # otherwise fall back to the current market price.
            avg_buy_price = price
            if pos.acquisition_value is not None and quantity:
                try:
                    avg_buy_price = Decimal(str(pos.acquisition_value)) / Decimal(str(quantity))
                except Exception:
                    avg_buy_price = price

            unrealized_pnl = (
                Decimal(str(pos.unrealized_pnl)) if pos.unrealized_pnl is not None else Decimal("0")
            )
            unrealized_pnl_pct = (
                Decimal(str(pos.unrealized_pnl_pct)) if pos.unrealized_pnl_pct is not None else Decimal("0")
            )

            # Create holding
            holding = PortfolioHolding(
                portfolio_id=resolved_portfolio_id,
                instrument_id=instrument_id,
                broker_id=broker_id,
                quantity=quantity,
                avg_buy_price=avg_buy_price,
                current_price=price,
                current_value=total_value,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
            )
            db.add(holding)
            await db.flush()
            await db.refresh(holding)
            holdings_created += 1

            # Create BUY trade
            trade = Trade(
                portfolio_id=resolved_portfolio_id,
                holding_id=holding.id,
                instrument_id=instrument_id,
                broker_id=broker_id,
                trade_type="BUY",
                trade_date=date.today(),
                quantity=quantity,
                price=price,
                total_amount=total_value,
                fees=Decimal("0"),
                notes=f"Imported from broker file: {upload.original_filename}"
                + (f" -- {pos.ticker}" if pos.ticker else ""),
            )
            db.add(trade)
            trades_created += 1

        except Exception as exc:
            error_msg = f"Failed to import position '{pos.ticker or pos.name}': {exc}"
            errors.append(error_msg)
            continue

    return BrokerFileImportResult(
        upload_id=upload.id,
        portfolio_id=resolved_portfolio_id,
        holdings_created=holdings_created,
        trades_created=trades_created,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Update / Delete
# ---------------------------------------------------------------------------

@router.put("/{upload_id}", response_model=BrokerFileUploadRead)
async def update_upload(
    upload_id: UUID,
    body: BrokerFileUploadUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update upload notes only."""
    upload = await _get_upload_or_404(db, upload_id, current_user.family_id)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(upload, field, value)

    parsed_data = None
    if upload.parsed_data:
        parsed_data = [
            BrokerPositionExtracted(
                ticker=p.get("ticker"),
                name=p.get("name") or p.get("title", ""),
                quantity=_safe_float(p.get("quantity") or p.get("quantity_total")),
                price=_safe_float(p["price"]) if p.get("price") is not None else None,
                value=_safe_float(p["value"]) if p.get("value") is not None else None,
                instrument_type=p.get("instrument_type") or p.get("instrument_class", ""),
                raw_data=p.get("raw_data"),
            )
            for p in upload.parsed_data
        ]

    return BrokerFileUploadRead(
        id=upload.id,
        family_id=upload.family_id,
        user_id=upload.user_id,
        broker_id=upload.broker_id,
        portfolio_id=upload.portfolio_id,
        original_filename=upload.original_filename,
        stored_filename=upload.stored_filename,
        s3_key=upload.s3_key,
        file_size=upload.file_size,
        file_type=upload.file_type,
        status=upload.status,
        parsed_data=parsed_data,
        error_message=upload.error_message,
        notes=upload.notes,
        created_at=upload.created_at,
        updated_at=upload.updated_at,
    )


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_upload(
    upload_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Soft delete an upload and its associated storage file.
    """
    upload = await _get_upload_or_404(db, upload_id, current_user.family_id)

    # Delete from storage (S3 or local)
    if upload.s3_key.startswith("local://"):
        try:
            local_path = upload.s3_key.replace("local://", "")
            os.unlink(local_path)
        except OSError as exc:
            logger.warning("Failed to delete local file %s: %s", upload.s3_key, exc)
    else:
        try:
            s3 = get_s3_client()
            s3.delete_object(Bucket=settings.s3_bucket, Key=upload.s3_key)
        except Exception as exc:
            logger.warning("Failed to delete S3 object %s: %s", upload.s3_key, exc)

    # Soft delete the DB record
    upload.soft_delete()
    return None


# ---------------------------------------------------------------------------
# Detect endpoint (NEW - for debugging file types)
# ---------------------------------------------------------------------------

@router.post("/{upload_id}/detect")
async def detect_upload_type(
    upload_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Debug endpoint: returns the detected file type and scores without processing.
    Useful for troubleshooting why a file isn't recognized.
    """
    upload = await _get_upload_or_404(db, upload_id, current_user.family_id)

    try:
        file_bytes = await _read_upload_file(upload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"File read failed: {exc}")

    tmp_path = _save_temp_file(file_bytes, upload.original_filename or upload.stored_filename)
    try:
        detection = detect_only(tmp_path)
        return {
            "upload_id": str(upload.id),
            "filename": upload.original_filename,
            "detected_parser": detection.get("detected"),
            "score": detection.get("score"),
            "all_scores": detection.get("all_scores"),
            "admin_only": detection.get("admin_only"),
            "file_hash": detection.get("file_hash"),
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _get_content_type(ext: str) -> str:
    """Return the MIME content type for a file extension."""
    mime_types = {
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "pdf": "application/pdf",
        "txt": "text/plain",
    }
    return mime_types.get(ext, "application/octet-stream")
