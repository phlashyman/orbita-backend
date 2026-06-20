"""
Tabela de Noticias do Mercado (AI Generated + Curated).
Suporta workflow: DRAFT -> PENDING_REVIEW -> PUBLISHED / REJECTED.
"""
import enum
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from app.database import Base
from app.utils.base import BaseMixin


class NewsStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"


class MarketNews(Base, BaseMixin):
    __tablename__ = "market_news"

    title = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    source = Column(String(100), default="AI Generated", nullable=False)
    source_url = Column(String(512), nullable=True)
    author = Column(String(100), nullable=True)
    category = Column(String(50), nullable=True)  # macro, bodiva, fiscal, corporate, market
    status = Column(String(30), default=NewsStatus.DRAFT.value, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    ai_model = Column(String(50), nullable=True)  # claude-3.5-sonnet, etc.
    ai_prompt_version = Column(String(20), nullable=True)
    tags = Column(String(300), nullable=True)  # comma-separated tags
    image_url = Column(String(512), nullable=True)
