-- =====================================================================
-- Órbita — Schema PostgreSQL das tabelas tocadas pela ingestão
-- Adaptado do SQLite. Seguro para correr: usa CREATE TABLE IF NOT EXISTS
-- (as tabelas que já existem no teu backend NÃO são alteradas).
--
-- NOTA asyncpg: os numéricos são DOUBLE PRECISION (não NUMERIC) de propósito.
-- O asyncpg é estrito com NUMERIC (exige decimal.Decimal e rejeita float); os
-- parsers produzem float, por isso DOUBLE PRECISION evita erros de tipo.
-- Datas/timestamps são DATE/TIMESTAMP; o persistence_async.py converte as
-- strings ISO dos parsers para date/datetime antes do INSERT.
-- =====================================================================

-- 1. CARTEIRAS (já existe no teu backend) --------------------------------
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             INTEGER,
    portfolio_id        INTEGER,
    broker              TEXT NOT NULL,
    ticker              TEXT NOT NULL,
    title               TEXT,
    snapshot_date       DATE NOT NULL,
    quantity_total      DOUBLE PRECISION,
    quantity_available  DOUBLE PRECISION,
    par_value_unit      DOUBLE PRECISION,
    quote_price         DOUBLE PRECISION,
    currency            TEXT DEFAULT 'AOA',
    current_value       DOUBLE PRECISION,
    acquisition_value   DOUBLE PRECISION,
    current_value_aoa   DOUBLE PRECISION,
    unrealized_pnl      DOUBLE PRECISION,
    daily_variation_aoa DOUBLE PRECISION,
    daily_variation_pct DOUBLE PRECISION,
    weight_pct          DOUBLE PRECISION,
    imported_at         TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_portfolio_snap UNIQUE (broker, ticker, snapshot_date)
    -- Multi-utilizador: a UNIQUE não inclui user_id; dois utilizadores com
    -- broker='AUREA' + mesmo ticker/data colidiriam. Recomendado evoluir para
    -- UNIQUE (user_id, broker, ticker, snapshot_date) numa migração.
);

-- 2. MESTRE DE INSTRUMENTOS ----------------------------------------------
CREATE TABLE IF NOT EXISTS bond_master (
    ticker           TEXT PRIMARY KEY,
    isin             TEXT,
    title            TEXT,
    issuer           TEXT,
    instrument_class TEXT,
    typology         TEXT,
    category         TEXT,
    currency         TEXT DEFAULT 'AOA',
    par_value        DOUBLE PRECISION,
    coupon_rate      DOUBLE PRECISION,
    frequency        TEXT,
    frequency_n      INTEGER,
    day_count        TEXT,
    issue_date       DATE,
    maturity_date    DATE,
    admission_date   DATE,
    qty_issued       BIGINT,
    issue_amount     DOUBLE PRECISION,
    bodiva_admitted  INTEGER DEFAULT 1,
    tax_regime       TEXT,
    coupon_tax_rate  DOUBLE PRECISION,
    capgain_tax_rate DOUBLE PRECISION,
    data_source      TEXT
);

-- 3. LIVRO DE ORDENS (formato 'long') -----------------------------------
CREATE TABLE IF NOT EXISTS order_book_snapshots (
    id            BIGSERIAL PRIMARY KEY,
    ticker        TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    snapshot_time TEXT,
    side          TEXT NOT NULL,            -- 'BID' | 'ASK'
    level         INTEGER NOT NULL,
    quantity      DOUBLE PRECISION,
    price         DOUBLE PRECISION,
    yield_pct     DOUBLE PRECISION,
    last_quote    DOUBLE PRECISION,
    imported_at   TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_order_book UNIQUE (ticker, snapshot_date, snapshot_time, side, level)
    -- Sem coluna 'source' (Aurea vs BODIVA). Para distinguir:
    --   ALTER TABLE order_book_snapshots ADD COLUMN source TEXT;
);

-- 4. MERCADO (cotações intraday/fecho) — já existe ----------------------
CREATE TABLE IF NOT EXISTS market_snapshots (
    id               BIGSERIAL PRIMARY KEY,
    ticker           TEXT NOT NULL,
    snapshot_date    DATE NOT NULL,
    snapshot_time    TEXT,
    source           TEXT NOT NULL,         -- 'aurea_destaques'|'bodiva_resumo'|'bodiva_boletim'
    instrument_class TEXT,
    price            DOUBLE PRECISION,
    currency         TEXT DEFAULT 'AOA',
    var_daily_pct    DOUBLE PRECISION,
    best_bid         DOUBLE PRECISION,
    best_ask         DOUBLE PRECISION,
    n_trades_day     INTEGER,
    volume_qty       DOUBLE PRECISION,
    volume_aoa       DOUBLE PRECISION,
    volume_trades    INTEGER,
    imported_at      TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_market_snap UNIQUE (ticker, snapshot_date, snapshot_time, source)
);

-- 5. CURVA DE RENDIMENTOS (Boletim) — já existe -------------------------
CREATE TABLE IF NOT EXISTS yield_curve_history (
    id                  BIGSERIAL PRIMARY KEY,
    snapshot_date       DATE NOT NULL,
    currency            TEXT DEFAULT 'AOA',
    maturity_label      TEXT NOT NULL,       -- '3M','6M','1Y'...
    yield_pct           DOUBLE PRECISION,
    var_pp_vs_yesterday DOUBLE PRECISION,
    CONSTRAINT uq_yield_curve UNIQUE (snapshot_date, currency, maturity_label)
);

-- 6. EVENTOS DE RENDIMENTO (Boletim) — já existe ------------------------
CREATE TABLE IF NOT EXISTS income_events (
    id            BIGSERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    ticker        TEXT,
    isin          TEXT,
    issuer        TEXT,
    currency      TEXT,
    event_type    TEXT,
    CONSTRAINT uq_income_events UNIQUE (snapshot_date, ticker, event_type)
);

-- 7. AGREGADOS MENSAIS / TRIMESTRAIS (Relatórios) -----------------------
CREATE TABLE IF NOT EXISTS bodiva_monthly_aggregates (
    id        BIGSERIAL PRIMARY KEY,
    year      INTEGER, month INTEGER, quarter INTEGER,
    segment   TEXT, ticker TEXT,
    montante  DOUBLE PRECISION, volume DOUBLE PRECISION, trades INTEGER,
    raw_json  TEXT,
    CONSTRAINT uq_monthly_agg UNIQUE (year, month, quarter, ticker)
);
CREATE TABLE IF NOT EXISTS bodiva_quarterly_aggregates (
    id        BIGSERIAL PRIMARY KEY,
    year      INTEGER, month INTEGER, quarter INTEGER,
    segment   TEXT, ticker TEXT,
    montante  DOUBLE PRECISION, volume DOUBLE PRECISION, trades INTEGER,
    raw_json  TEXT,
    CONSTRAINT uq_quarterly_agg UNIQUE (year, month, quarter, ticker)
);

-- 8. AUDITORIA DE IMPORTAÇÕES — já existe -------------------------------
--    O persistence_async só escreve as colunas que existirem; confirma que
--    a tua import_log tem (pelo menos) file_hash, status e parser_name para
--    a idempotência por ficheiro funcionar.
CREATE TABLE IF NOT EXISTS import_log (
    id               BIGSERIAL PRIMARY KEY,
    user_id          INTEGER,
    parser_name      TEXT,
    file_hash        TEXT,
    snapshot_date    DATE,
    status           TEXT,                  -- 'success'|'failed'|'skipped'
    rows_processed   INTEGER,
    rows_applied     INTEGER,
    rows_skipped     INTEGER,
    warnings         TEXT,
    errors           TEXT,
    summary          TEXT,
    duration_seconds DOUBLE PRECISION,
    imported_at      TIMESTAMPTZ DEFAULT now()
);

-- Índices ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_import_hash ON import_log (file_hash);
CREATE INDEX IF NOT EXISTS idx_market_ticker_date ON market_snapshots (ticker, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_ob_ticker_date ON order_book_snapshots (ticker, snapshot_date);

-- =====================================================================
-- Já existem no teu backend: portfolio_snapshots, broker_file_uploads,
-- market_snapshots, yield_curve_history, income_events, import_log.
-- Provavelmente FALTAM (os parsers escrevem nelas): bond_master,
-- order_book_snapshots, bodiva_monthly_aggregates, bodiva_quarterly_aggregates.
-- Os CREATE IF NOT EXISTS acima criam só o que faltar, sem mexer no resto.
-- =====================================================================
