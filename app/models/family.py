"""
Tabela de Famílias (Tenant Core).
Every family is an isolated tenant — all user data is scoped by family_id.
"""
from sqlalchemy import Column, String
from app.database import Base
from app.utils.base import BaseMixin


class Family(Base, BaseMixin):
    __tablename__ = "families"

    name = Column(String(100), nullable=False)
