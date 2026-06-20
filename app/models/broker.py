"""
Tabela de Corretoras (Brokers).
Reference data for Angolan brokerage firms where users hold positions.
"""
from sqlalchemy import Column, String, Boolean
from app.database import Base
from app.utils.base import BaseMixin


class Broker(Base, BaseMixin):
    __tablename__ = "brokers"

    name = Column(String(100), nullable=False)           # e.g. "BFA", "BCI", "FSDEA"
    full_name = Column(String(200), nullable=True)       # e.g. "Banco de Fomento Angola"
    code = Column(String(20), unique=True, nullable=False) # Internal code
    is_active = Column(Boolean, default=True, nullable=False)
