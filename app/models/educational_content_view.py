"""
Tracking de visualizações de conteúdos educacionais (Orbita Academy).
Usado para recomendar conteúdos e medir engajamento.
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from app.database import Base
from app.utils.base import BaseMixin


class EducationalContentView(Base, BaseMixin):
    """
    Registo de quando um utilizador vê um conteúdo educacional.
    """
    __tablename__ = "educational_content_views"

    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Identificação do conteúdo
    content_key = Column(
        String(100), nullable=False,
        comment="Chave única: 'glossary.ytm', 'explain.duration', 'calculator.dca'",
    )
    content_type = Column(
        String(50), nullable=False,
        comment="glossary / explain / calculator / tooltip / ips",
    )

    # Metadados
    level = Column(
        String(20), nullable=True,
        comment="beginner / intermediate / advanced",
    )
    viewed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    view_duration_seconds = Column(Integer, nullable=True)
