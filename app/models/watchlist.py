"""
Watchlist de activos internacionais por utilizador.
Cada item guarda ticker + exchange + nome para exibição,
mais metadados opcionais (sector, notas).
"""
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.utils.base import BaseMixin


class WatchlistItem(Base, BaseMixin):
    __tablename__ = "watchlist_items"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker = Column(String(20), nullable=False)
    exchange = Column(String(30), nullable=False)
    name = Column(String(200), nullable=True)      # cached display name
    sector = Column(String(100), nullable=True)
    notes = Column(String(500), nullable=True)
