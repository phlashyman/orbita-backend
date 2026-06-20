"""Add investment models: profiles, analytics, scenarios, signals, goals, and more.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === 1. Investor Profile ===
    op.create_table(
        "investor_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", sa.Enum("RAPIDO", "COMPLETO", name="quizmode"), nullable=False),
        sa.Column("tolerancia_risco", sa.Float(), nullable=True),
        sa.Column("horizonte_temporal", sa.Float(), nullable=True),
        sa.Column("objectivos_retorno", sa.Float(), nullable=True),
        sa.Column("capacidade_financeira", sa.Float(), nullable=True),
        sa.Column("conhecimento", sa.Float(), nullable=True),
        sa.Column("score_total", sa.Float(), nullable=False),
        sa.Column("perfil", sa.Enum("CONSERVADOR", "MODERADO", "DINAMICO", "AGRESSIVO", name="investorriskprofile"), nullable=False),
        sa.Column("alocacao_sugerida", postgresql.JSON(), nullable=True),
        sa.Column("respostas", postgresql.JSON(), nullable=True),
        sa.Column("quiz_date", sa.Date(), nullable=False),
        sa.Column("ips_url", sa.String(500), nullable=True),
        sa.Column("recommended_strategies", postgresql.JSON(), nullable=True),
    )

    # === 2. Portfolio Analytics ===
    op.create_table(
        "portfolio_analytics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("var_95_1m", sa.Float(), nullable=True),
        sa.Column("var_95_1m_pct", sa.Float(), nullable=True),
        sa.Column("cvar_95_1m", sa.Float(), nullable=True),
        sa.Column("sharpe_ratio", sa.Float(), nullable=True),
        sa.Column("sortino_ratio", sa.Float(), nullable=True),
        sa.Column("calmar_ratio", sa.Float(), nullable=True),
        sa.Column("information_ratio", sa.Float(), nullable=True),
        sa.Column("macaulay_duration", sa.Float(), nullable=True),
        sa.Column("modified_duration", sa.Float(), nullable=True),
        sa.Column("convexity", sa.Float(), nullable=True),
        sa.Column("hhi", sa.Float(), nullable=True),
        sa.Column("gini", sa.Float(), nullable=True),
        sa.Column("effective_n", sa.Float(), nullable=True),
        sa.Column("liquidity_score", sa.Float(), nullable=True),
        sa.Column("estimated_slippage_pct", sa.Float(), nullable=True),
        sa.Column("max_drawdown_pct", sa.Float(), nullable=True),
        sa.Column("max_drawdown_duration_days", sa.Integer(), nullable=True),
        sa.Column("snapshot_date", sa.DateTime(), nullable=False),
        sa.Column("portfolio_value", sa.Float(), nullable=True),
        sa.Column("total_invested", sa.Float(), nullable=True),
        sa.Column("unrealized_pnl", sa.Float(), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("raw_data", postgresql.JSON(), nullable=True),
    )

    # === 3. Scenario Analysis ===
    op.create_table(
        "scenario_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scenario_type", sa.Enum("PARAMETRIC", "MONTE_CARLO", "SENSITIVITY", "CUSTOM", name="scenariotype"), nullable=False),
        sa.Column("scenario_name", sa.String(100), nullable=True),
        sa.Column("params", postgresql.JSON(), nullable=True),
        sa.Column("impact_value", sa.Float(), nullable=True),
        sa.Column("impact_pct", sa.Float(), nullable=True),
        sa.Column("probability", sa.Float(), nullable=True),
        sa.Column("distribution", postgresql.JSON(), nullable=True),
        sa.Column("n_simulations", sa.Integer(), nullable=True),
        sa.Column("confidence_level", sa.Float(), nullable=True),
        sa.Column("snapshot_date", sa.DateTime(), nullable=False),
    )

    # === 4. Scenario Definition ===
    op.create_table(
        "scenario_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("category", sa.Enum("MACRO", "CREDIT", "CURRENCY", "COMMODITY", "POLITICAL", "CUSTOM", name="scenariocategory"), nullable=False),
        sa.Column("params_schema", postgresql.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("severity", sa.Integer(), default=0),
    )

    # === 5. Investment Signal ===
    op.create_table(
        "investment_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=True),
        sa.Column("signal_type", sa.Enum("SWAP", "BUY", "SELL", "HOLD", "DCA", "BULLET", "BARBELL", "LADDER", "REBALANCE", "RISK_ALERT", "MARKET_SIGNAL", name="signaltype"), nullable=False),
        sa.Column("severity", sa.Enum("INFO", "WATCH", "ALERT", "CRITICAL", name="signalseverity"), default="INFO"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_ticker", sa.String(20), nullable=True),
        sa.Column("target_ticker", sa.String(20), nullable=True),
        sa.Column("estimated_benefit", sa.Float(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("action_url", sa.String(500), nullable=True),
        sa.Column("is_actionable", sa.Boolean(), default=False),
        sa.Column("is_dismissed", sa.Boolean(), default=False),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
    )

    # === 6. Investment Goal ===
    op.create_table(
        "investment_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("target_amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(3), default="AOA"),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("monthly_saving", sa.Float(), nullable=True),
        sa.Column("current_amount", sa.Float(), default=0.0),
        sa.Column("initial_amount", sa.Float(), default=0.0),
        sa.Column("progress_pct", sa.Float(), default=0.0),
        sa.Column("status", sa.Enum("ACTIVE", "COMPLETED", "CANCELLED", "ON_TRACK", "BEHIND", name="goalstatus"), default="ACTIVE"),
        sa.Column("priority", sa.Integer(), default=0),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("notes", postgresql.JSON(), nullable=True),
    )

    # === 7. AI Assistant Log ===
    op.create_table(
        "ai_assistant_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=True),
        sa.Column("feature", sa.Enum("PORTFOLIO_ANALYSIS", "CHAT", "WEEKLY_REPORT", "ALERT", "NEWS", "AUTO_INSIGHT", "PORTFOLIO_BUILDER", name="aifeature"), nullable=False),
        sa.Column("model", sa.String(50), nullable=False),
        sa.Column("tokens_input", sa.Integer(), nullable=True),
        sa.Column("tokens_output", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("user_message", sa.Text(), nullable=True),
        sa.Column("response_excerpt", sa.String(500), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("was_capped", sa.Boolean(), default=False),
        sa.Column("cache_hit", sa.Boolean(), default=False),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
    )

    # === 8. Educational Content View ===
    op.create_table(
        "educational_content_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_key", sa.String(100), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("level", sa.String(20), nullable=True),
        sa.Column("viewed_at", sa.DateTime(), nullable=False),
        sa.Column("view_duration_seconds", sa.Integer(), nullable=True),
    )

    # === 9. Currency Pair ===
    op.create_table(
        "currency_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pair", sa.String(7), nullable=False, index=True),
        sa.Column("bid", sa.Float(), nullable=True),
        sa.Column("ask", sa.Float(), nullable=True),
        sa.Column("mid", sa.Float(), nullable=False),
        sa.Column("variation_pct", sa.Float(), nullable=True),
        sa.Column("source", sa.String(50), default="bna"),
        sa.Column("snapshot_date", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("pair", "snapshot_date", name="uq_currency_pair_date"),
    )

    # === 10. International Position ===
    op.create_table(
        "international_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("exchange", sa.String(20), nullable=True),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("currency", sa.String(3), default="USD"),
        sa.Column("market", sa.String(50), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("purchase_price", sa.Float(), nullable=True),
        sa.Column("purchase_price_currency", sa.String(3), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("current_price_date", sa.Date(), nullable=True),
        sa.Column("current_value_aoa", sa.Float(), nullable=True),
        sa.Column("unrealized_pnl", sa.Float(), nullable=True),
        sa.Column("unrealized_pnl_pct", sa.Float(), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
    )

    # === 11. Market Comparison ===
    op.create_table(
        "market_comparisons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("initial_amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(3), default="AOA"),
        sa.Column("results", postgresql.JSON(), nullable=False),
        sa.Column("years", sa.Float(), nullable=True),
        sa.Column("inflation_rate", sa.Float(), nullable=True),
        sa.Column("usd_aoa_start", sa.Float(), nullable=True),
        sa.Column("usd_aoa_end", sa.Float(), nullable=True),
        sa.Column("calculated_at", sa.DateTime(), nullable=False),
    )

    # === 12. Country Risk Metric ===
    op.create_table(
        "country_risk_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("country", sa.String(50), default="Angola"),
        sa.Column("country_code", sa.String(3), default="AO"),
        sa.Column("crp", sa.Float(), nullable=True),
        sa.Column("rating", sa.String(5), nullable=True),
        sa.Column("cds_spread", sa.Integer(), nullable=True),
        sa.Column("bna_rate", sa.Float(), nullable=True),
        sa.Column("inflation_rate", sa.Float(), nullable=True),
        sa.Column("usd_aoa", sa.Float(), nullable=True),
        sa.Column("gdp_growth", sa.Float(), nullable=True),
        sa.Column("erp", sa.Float(), nullable=True),
        sa.Column("risk_free_rate", sa.Float(), nullable=True),
        sa.Column("liquidity_premium", sa.Float(), default=0.02),
        sa.Column("source", sa.String(50), default="damodaran+bna+ine"),
        sa.Column("created_at_ts", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("metric_date", name="uq_country_risk_date"),
    )

    # === 13. Tax Rule ===
    op.create_table(
        "tax_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("instrument_class", sa.String(20), nullable=False),
        sa.Column("bodiva_admitted", sa.Boolean(), default=True),
        sa.Column("coupon_tax_rate", sa.Float(), nullable=False),
        sa.Column("capgain_tax_rate", sa.Float(), nullable=True),
        sa.Column("stamp_duty", sa.Float(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("priority", sa.Integer(), default=0),
    )


def downgrade() -> None:
    op.drop_table("tax_rules")
    op.drop_table("country_risk_metrics")
    op.drop_table("market_comparisons")
    op.drop_table("international_positions")
    op.drop_table("currency_pairs")
    op.drop_table("educational_content_views")
    op.drop_table("ai_assistant_logs")
    op.drop_table("investment_goals")
    op.drop_table("investment_signals")
    op.drop_table("scenario_definitions")
    op.drop_table("scenario_analyses")
    op.drop_table("portfolio_analytics")
    op.drop_table("investor_profiles")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS quizmode CASCADE")
    op.execute("DROP TYPE IF EXISTS investorriskprofile CASCADE")
    op.execute("DROP TYPE IF EXISTS scenariotype CASCADE")
    op.execute("DROP TYPE IF EXISTS scenariocategory CASCADE")
    op.execute("DROP TYPE IF EXISTS signaltype CASCADE")
    op.execute("DROP TYPE IF EXISTS signalseverity CASCADE")
    op.execute("DROP TYPE IF EXISTS goalstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS aifeature CASCADE")
