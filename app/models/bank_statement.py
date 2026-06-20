"""
Tabela de Linhas do Extrato Bancário Importado.
Each row represents a line from an imported bank statement.
Unique constraint on (account_id, bank_transaction_id) prevents duplicates.
"""
import enum
from sqlalchemy import Column, ForeignKey, Numeric, Date, String, UniqueConstraint
from app.database import Base
from app.utils.base import BaseMixin


class StatementStatus(str, enum.Enum):
    UNMATCHED = "UNMATCHED"
    MATCHED = "MATCHED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class BankStatement(Base, BaseMixin):
    __tablename__ = "bank_statements"

    family_id = Column(
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id = Column(
        ForeignKey("bank_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Hash único da linha para evitar duplicidade na importação
    bank_transaction_id = Column(String(255), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    date = Column(Date, nullable=False)
    description_raw = Column(String(255), nullable=False)
    status = Column(
        String(30),
        default=StatementStatus.UNMATCHED.value,
        nullable=False,
    )
    assigned_user_id = Column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Unique constraint: same account + same transaction ID = duplicate
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "bank_transaction_id",
            name="unique_bank_tx",
        ),
    )
