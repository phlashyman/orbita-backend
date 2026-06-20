"""
Tabela de Contas Bancárias / Carteiras.
Supports multiple banks (BAI, BFA, BCI, etc.) and account types.
"""
import enum
from sqlalchemy import Column, String, ForeignKey
from app.database import Base
from app.utils.base import BaseMixin


class AccountType(str, enum.Enum):
    CURRENT = "CURRENT"
    SAVINGS = "SAVINGS"
    CASH = "CASH"


class BankAccount(Base, BaseMixin):
    __tablename__ = "bank_accounts"

    family_id = Column(
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    bank_name = Column(String(100), nullable=False)  # BAI, BFA, BCI, Caixa Carteira
    account_type = Column(
        String(50),
        default=AccountType.CURRENT.value,
        nullable=False,
    )
    currency = Column(String(3), default="AOA", nullable=False)
