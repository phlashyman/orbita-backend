-- =====================================================================
-- Órbita — Permite holdings sem instrumento mapeado
--
-- O endpoint /portfolio/uploads/{id}/import cria PortfolioHolding mesmo
-- quando o ticker do ficheiro do broker não corresponde a nenhum
-- instrumento na tabela `instruments` (instrument_id = NULL).
-- A coluna estava NOT NULL com ON DELETE CASCADE, o que causava um
-- NotNullViolationError (HTTP 500) em todos os imports cujo ticker não
-- estivesse pré-cadastrado em `instruments`.
-- =====================================================================

ALTER TABLE portfolio_holdings
    DROP CONSTRAINT IF EXISTS portfolio_holdings_instrument_id_fkey;

ALTER TABLE portfolio_holdings
    ALTER COLUMN instrument_id DROP NOT NULL;

ALTER TABLE portfolio_holdings
    ADD CONSTRAINT portfolio_holdings_instrument_id_fkey
    FOREIGN KEY (instrument_id) REFERENCES instruments(id) ON DELETE SET NULL;
