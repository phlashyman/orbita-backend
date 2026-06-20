"""
Tabela de Log de Conciliação (Tabela de Junção/Auditoria).
Records every match between a manual transaction and a bank statement line.
Every insert/update here must be inside an ACID transaction.
"""
from sqlalchemy import Column, ForeignKey, DateTime
from app.database import Base
from app.utils.base import BaseMixin
from datetime import datetime, timezone


class ConciliationLog(Base, BaseMixin):
    __tablename__ = "conciliations_log"

    family_id = Column(
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    transaction_manual_id = Column(
        ForeignKey("transactions_manual.id", ondelete="CASCADE"),
        nullable=False,
    )
    bank_statement_id = Column(
        ForeignKey("bank_statements.id", ondelete="CASCADE"),
        nullable=False,
    )
    conciliated_by = Column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    conciliated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
