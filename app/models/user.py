"""
Tabela de Utilizadores e Permissões.

Role hierarchy:
  ADMIN  — Orbita platform operator.  Manages market data and instruments.
            Does not have personal portfolios or broker file uploads.
  GESTOR — Gestor da Família.  Primary user of a family group.  Created via
            registration.  Full access to all user-facing pages (portfolio,
            investments, budget, reconciliation…) and can add/remove members.
  MEMBER — Family member added by a GESTOR.  Access to shared family pages.
"""
import enum
from sqlalchemy import Column, String, ForeignKey, Enum
from app.database import Base
from app.utils.base import BaseMixin


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"    # Platform operator (Orbita team)
    GESTOR = "GESTOR"  # Gestor da Família — family head
    MEMBER = "MEMBER"  # Family member added by Gestor


class User(Base, BaseMixin):
    __tablename__ = "users"

    family_id = Column(
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.MEMBER, nullable=False)
