"""
Broker File Upload model.

Stores uploaded portfolio statement files from Angolan brokers (BFA, BCI, etc.).
Files are stored in S3; metadata and extracted positions are kept in PostgreSQL.
"""
from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON

from app.database import Base
from app.utils.base import BaseMixin


class BrokerFileUpload(Base, BaseMixin):
    """
    Represents an uploaded broker file (CSV, XLSX, PDF, TXT).

    Lifecycle:
        PENDING    → file uploaded, awaiting processing
        PROCESSING → parser is running
        PROCESSED  → positions extracted successfully
        ERROR      → parsing failed
    """

    __tablename__ = "broker_file_uploads"

    # Foreign keys
    family_id = Column(
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    broker_id = Column(
        ForeignKey("brokers.id", ondelete="SET NULL"),
        nullable=True,
    )
    portfolio_id = Column(
        ForeignKey("portfolios.id", ondelete="SET NULL"),
        nullable=True,
    )

    # File metadata
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)  # UUID-based
    s3_key = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=True)  # bytes
    file_type = Column(String(10), nullable=False)  # CSV, XLSX, PDF, TXT

    # Processing status
    status = Column(
        String(20),
        default="PENDING",
        nullable=False,
    )  # PENDING, PROCESSING, PROCESSED, ERROR
    parsed_data = Column(JSON, nullable=True)  # Extracted positions as JSON
    error_message = Column(Text, nullable=True)

    # User notes
    notes = Column(String(500), nullable=True)
