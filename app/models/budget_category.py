"""
Tabela de Categorias do Orçamento Unificado.
Categories are scoped by family and month_year for time-boxed budgeting.
"""
from sqlalchemy import Column, String, ForeignKey, Numeric, Date
from app.database import Base
from app.utils.base import BaseMixin


class BudgetCategory(Base, BaseMixin):
    __tablename__ = "budget_categories"

    family_id = Column(
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(100), nullable=False)  # Groceries, Transport, Lazer
    projected_amount = Column(
        Numeric(15, 2),
        default=0.00,
        nullable=False,
    )
    month_year = Column(Date, nullable=False)  # 2026-05-01 (first day of month)
