"""
SQLAlchemy models for BODIVA market data ingestion tables.
These mirror the schema in alembic/versions/004_schema_postgresql.sql.
All tables use BIGSERIAL PKs (Integer autoincrement) — no BaseMixin UUID.
"""
from sqlalchemy import (
    Column, Integer, BigInteger, Text, Float, Date, DateTime,
    String, UniqueConstraint, Index, func,
)
from app.database import Base


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (
        UniqueConstraint("ticker", "snapshot_date", "snapshot_time", "source",
                         name="uq_market_snap"),
        Index("idx_market_ticker_date", "ticker", "snapshot_date"),
    )

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    ticker           = Column(Text, nullable=False)
    snapshot_date    = Column(Date, nullable=False)
    snapshot_time    = Column(Text)
    source           = Column(Text, nullable=False)
    instrument_class = Column(Text)
    price            = Column(Float)
    currency         = Column(Text, default="AOA")
    var_daily_pct    = Column(Float)
    best_bid         = Column(Float)
    best_ask         = Column(Float)
    n_trades_day     = Column(Integer)
    volume_qty       = Column(Float)
    volume_aoa       = Column(Float)
    volume_trades    = Column(Integer)
    imported_at      = Column(DateTime(timezone=True), server_default=func.now())


class OrderBookSnapshot(Base):
    __tablename__ = "order_book_snapshots"
    __table_args__ = (
        UniqueConstraint("ticker", "snapshot_date", "snapshot_time", "side", "level",
                         name="uq_order_book"),
        Index("idx_ob_ticker_date", "ticker", "snapshot_date"),
    )

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    ticker        = Column(Text, nullable=False)
    snapshot_date = Column(Date, nullable=False)
    snapshot_time = Column(Text)
    side          = Column(Text, nullable=False)   # 'BID' | 'ASK'
    level         = Column(Integer, nullable=False)
    quantity      = Column(Float)
    price         = Column(Float)
    yield_pct     = Column(Float)
    last_quote    = Column(Float)
    imported_at   = Column(DateTime(timezone=True), server_default=func.now())


class BondMaster(Base):
    __tablename__ = "bond_master"

    ticker           = Column(Text, primary_key=True)
    isin             = Column(Text)
    title            = Column(Text)
    issuer           = Column(Text)
    instrument_class = Column(Text)
    typology         = Column(Text)
    category         = Column(Text)
    currency         = Column(Text, default="AOA")
    par_value        = Column(Float)
    coupon_rate      = Column(Float)
    frequency        = Column(Text)
    frequency_n      = Column(Integer)
    day_count        = Column(Text)
    issue_date       = Column(Date)
    maturity_date    = Column(Date)
    admission_date   = Column(Date)
    qty_issued       = Column(BigInteger)
    issue_amount     = Column(Float)
    bodiva_admitted  = Column(Integer, default=1)
    tax_regime       = Column(Text)
    coupon_tax_rate  = Column(Float)
    capgain_tax_rate = Column(Float)
    data_source      = Column(Text)


class ImportLog(Base):
    __tablename__ = "import_log"
    __table_args__ = (
        Index("idx_import_hash", "file_hash"),
    )

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id          = Column(Integer)
    parser_name      = Column(Text)
    file_hash        = Column(Text)
    snapshot_date    = Column(Date)
    status           = Column(Text)
    rows_processed   = Column(Integer)
    rows_applied     = Column(Integer)
    rows_skipped     = Column(Integer)
    warnings         = Column(Text)
    errors           = Column(Text)
    summary          = Column(Text)
    duration_seconds = Column(Float)
    imported_at      = Column(DateTime(timezone=True), server_default=func.now())


class YieldCurveHistory(Base):
    __tablename__ = "yield_curve_history"
    __table_args__ = (
        UniqueConstraint("snapshot_date", "currency", "maturity_label",
                         name="uq_yield_curve"),
    )

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_date       = Column(Date, nullable=False)
    currency            = Column(Text, default="AOA")
    maturity_label      = Column(Text, nullable=False)
    yield_pct           = Column(Float)
    var_pp_vs_yesterday = Column(Float)


class IncomeEvent(Base):
    __tablename__ = "income_events"
    __table_args__ = (
        UniqueConstraint("snapshot_date", "ticker", "event_type",
                         name="uq_income_events"),
    )

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, nullable=False)
    ticker        = Column(Text)
    isin          = Column(Text)
    issuer        = Column(Text)
    currency      = Column(Text)
    event_type    = Column(Text)


class BodivaMonthlyAggregate(Base):
    __tablename__ = "bodiva_monthly_aggregates"
    __table_args__ = (
        UniqueConstraint("year", "month", "quarter", "ticker",
                         name="uq_monthly_agg"),
    )

    id       = Column(BigInteger, primary_key=True, autoincrement=True)
    year     = Column(Integer)
    month    = Column(Integer)
    quarter  = Column(Integer)
    segment  = Column(Text)
    ticker   = Column(Text)
    montante = Column(Float)
    volume   = Column(Float)
    trades   = Column(Integer)
    raw_json = Column(Text)


class BodivaQuarterlyAggregate(Base):
    __tablename__ = "bodiva_quarterly_aggregates"
    __table_args__ = (
        UniqueConstraint("year", "month", "quarter", "ticker",
                         name="uq_quarterly_agg"),
    )

    id       = Column(BigInteger, primary_key=True, autoincrement=True)
    year     = Column(Integer)
    month    = Column(Integer)
    quarter  = Column(Integer)
    segment  = Column(Text)
    ticker   = Column(Text)
    montante = Column(Float)
    volume   = Column(Float)
    trades   = Column(Integer)
    raw_json = Column(Text)
