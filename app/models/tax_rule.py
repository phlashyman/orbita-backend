"""
Regras fiscais — IAC (Imposto sobre Aplicações de Capital) e IRC.

IAC temporal (Lei 14/25 — OGE 2026):
  - 5% para rendimentos até 31/12/2025
  - 10% para rendimentos a partir de 01/01/2026 (abolido o regime reduzido)

Cada regra tem valid_from/valid_to para permitir alterações futuras da taxa.
"""
from datetime import date
from sqlalchemy import Column, String, Integer, Float, Boolean, Date, Text
from app.database import Base
from app.utils.base import BaseMixin


class TaxRule(Base, BaseMixin):
    """
    Regra fiscal para um tipo de instrumento e período.
    """
    __tablename__ = "tax_rules"

    # Identificação
    name = Column(String(100), nullable=False, comment="Ex: 'IAC OT-NR 2026'")
    description = Column(Text, nullable=True)

    # Aplicabilidade
    instrument_class = Column(
        String(20), nullable=False,
        comment="BOND_GOV / BOND_CORP / EQUITY / FUND / TBILL",
    )
    bodiva_admitted = Column(Boolean, default=True, comment="Apenas admitidos na BODIVA?")

    # Taxas (decimais: 0.10 = 10%)
    coupon_tax_rate = Column(Float, nullable=False, comment="IAC sobre cupões")
    capgain_tax_rate = Column(Float, nullable=True, comment="IRC sobre mais-valias")
    stamp_duty = Column(Float, nullable=True, comment="Imposto de selo")

    # Período de validade
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True, comment="NULL = vigente indefinidamente")

    # Metadados
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0, comment="Prioridade de resolução (maior = primeiro)")
