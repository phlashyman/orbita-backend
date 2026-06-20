"""
Tabela de Instrumentos do Mercado BODIVA.
Reference data for bonds, treasury bills, and other traded instruments.
"""
import enum
from sqlalchemy import Column, String, Numeric, Date, Integer, Boolean, Text
from app.database import Base
from app.utils.base import BaseMixin


class InstrumentType(str, enum.Enum):
    TREASURY_BOND = "TREASURY_BOND"       # OT - Obrigações do Tesouro
    TREASURY_BILL = "TREASURY_BILL"       # BT - Bilhetes do Tesouro
    CORPORATE_BOND = "CORPORATE_BOND"     # Obrigações corporativas
    COMMERCIAL_PAPER = "COMMERCIAL_PAPER" # Papel comercial
    CERTIFICATE = "CERTIFICATE"           # Certificados de depósito


class InterestType(str, enum.Enum):
    FIXED = "FIXED"
    FLOATING = "FLOATING"
    MIXED = "MIXED"


class Instrument(Base, BaseMixin):
    __tablename__ = "instruments"

    isin = Column(String(12), unique=True, nullable=False)
    ticker = Column(String(20), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    instrument_type = Column(String(50), nullable=False)
    issuer = Column(String(100), nullable=False)           # e.g. "Governo de Angola", "BFA"

    # Financial terms
    face_value = Column(Numeric(15, 2), nullable=False)    # Valor nominal (AOA)
    coupon_rate = Column(Numeric(5, 2), nullable=True)     # Taxa de cupão %
    interest_type = Column(String(20), default="FIXED", nullable=False)
    issue_date = Column(Date, nullable=False)
    maturity_date = Column(Date, nullable=False)
    frequency_months = Column(Integer, default=12, nullable=False)  # Pagamentos/ano (3, 6, 12)

    # Market data (updated periodically)
    current_price = Column(Numeric(15, 2), nullable=True)  # Preço atual de mercado
    current_yield = Column(Numeric(5, 2), nullable=True)   # Yield atual %

    # Tax
    withholding_tax = Column(Numeric(5, 2), default=10.00, nullable=False)  # Imposto retido na fonte %

    is_active = Column(Boolean, default=True, nullable=False)
    currency = Column(String(3), default="AOA", nullable=False)
