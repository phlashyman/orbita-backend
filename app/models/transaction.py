"""
Tabela de Transações Manuais (Executado pelos Utilizadores).
Each transaction is entered by a family member and can be linked to
a bank account, category, and receipt image.
"""
import enum
from sqlalchemy import Column, ForeignKey, Numeric, Date, String
from app.database import Base
from app.utils.base import BaseMixin


class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONCILED = "CONCILED"


class TransactionManual(Base, BaseMixin):
    __tablename__ = "transactions_manual"

    family_id = Column(
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    account_id = Column(
        ForeignKey("bank_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    category_id = Column(
        ForeignKey("budget_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    amount = Column(Numeric(15, 2), nullable=False)
    date = Column(Date, nullable=False)
    description = Column(String(255), nullable=True)
    receipt_url = Column(String(512), nullable=True)  # S3 path to receipt image
    status = Column(
        String(20),
        default=TransactionStatus.PENDING.value,
        nullable=False,
    )
