"""
Métricas de risco país para Angola.
Actualizado mensalmente (APScheduler) com dados de Damodaran, BNA, INE.

Fórmula ajustada para mercados fronteira:
  Ke = Rf + β × (ERP + CRP) + Liquidity Premium — inflação
"""
from datetime import datetime, date
from sqlalchemy import Column, String, Integer, Float, Date, DateTime, UniqueConstraint
from app.database import Base
from app.utils.base import BaseMixin


class CountryRiskMetric(Base, BaseMixin):
    """
    Snapshot de métricas de risco país para Angola num dado mês.
    """
    __tablename__ = "country_risk_metrics"
    __table_args__ = (
        UniqueConstraint("metric_date", name="uq_country_risk_date"),
    )

    # Data da métrica
    metric_date = Column(Date, nullable=False)

    # País
    country = Column(String(50), default="Angola")
    country_code = Column(String(3), default="AO")

    # Risco país (Damodaran)
    crp = Column(Float, nullable=True, comment="Country Risk Premium (Damodaran, %)")
    rating = Column(String(5), nullable=True, comment="Rating soberano (ex: B-, Caa1)")
    cds_spread = Column(Integer, nullable=True, comment="CDS Angola (bps)")

    # Macroeconomia
    bna_rate = Column(Float, nullable=True, comment="Taxa BNA (%)")
    inflation_rate = Column(Float, nullable=True, comment="Inflação anual (INE, %)")
    usd_aoa = Column(Float, nullable=True, comment="Taxa de câmbio USD/AOA")
    gdp_growth = Column(Float, nullable=True, comment="Crescimento PIB (%)")

    # Equity risk premium (Damodaran)
    erp = Column(Float, nullable=True, comment="Equity Risk Premium (Damodaran, %)")
    risk_free_rate = Column(Float, nullable=True, comment="Rf (OT 10yr benchmark, %)")

    # Liquidity premium (estimado)
    liquidity_premium = Column(Float, nullable=True, default=0.02, comment="Prémio de liquidez mercado fronteira")

    # Fonte
    source = Column(String(50), default="damodaran+bna+ine")

    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
