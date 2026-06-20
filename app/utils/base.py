"""
Base model mixin with UUID PK, timestamps, and soft delete.
All application models extend this mixin.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import UUID


class BaseMixin:
    """
    Mixin providing:
    - id: UUID primary key (auto-generated)
    - created_at: timestamp on creation
    - updated_at: timestamp on every update
    - deleted_at: soft delete timestamp (None = active)
    """

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = datetime.now(timezone.utc)
