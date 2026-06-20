## Handoff — Sprint 4 concluido

**Modelo:** Claude Opus 4.8 (🔵)
**Data:** 2026-06-20

---

### O que foi feito no Sprint 4

**Port dos tres motores financeiros do Claude AI para o novo backend FastAPI.**

1. **`app/services/financial_core.py`** (315 linhas)
   - `solve_ytm()` — Newton-Raphson com Decimal(28), 60 iteracoes max
   - `calc_duration()` — Macaulay, Modified, Convexity, PV teorico
   - `fisher_real()` — (1+Nominal)/(1+Inflacao) - 1
   - `calc_liquidation()` — Liquidacao T0 com comissao (0.395%) + IAC
   - `generate_cash_flows()` — Projeccao de cupoes + reembolso
   - `price_impact_yield_shock()` — 2a-ordem Taylor
   - `parse_date()`, `freq_n()`, `years_between()` — helpers data/frequencia
   - **Todas as funcoes PURAS** — sem DB, sem async, testaveis sem infra

2. **`app/services/tax_engine.py`** (109 linhas)
   - `resolve_tax_rates()` — query async SQLAlchemy a tabela `tax_rules`
   - Filtro temporal: `valid_from <= payment_date <= valid_to`
   - Fallback: 10% (regime actual Lei 14/25)
   - `resolve_for_bond()` — wrapper que aceita dict de bond_master
   - `get_active_iac_rate()` — wrapper minimal

3. **`app/services/cashflow_engine.py`** (208 linhas)
   - `bond_coupon_schedule()` — calendario de cupoes futuros com IAC por data
   - Enriquecimento automatico do BondMaster (async SQLAlchemy)
   - `portfolio_cashflows()` — agregacao de todos os bonds da carteira
   - `next_payment()` — proximo pagamento agregado (totais + tickers)
   - `monthly_cashflow_table()` — buckets mensais para graficos

### Verificacao

- `solve_ytm()`: convergente para OT-NR tipica (19.5% nominal)
- `fisher_real(0.20, 0.12)` = 7.14% — correcto
- Duration, Convexity, PriceImpact — valores plausiveis
- `calc_liquidation()`: 100 x 10K par @ 104% = 1,087,552.90 AOA

### Ficheiros criados
- `app/services/financial_core.py`
- `app/services/tax_engine.py`
- `app/services/cashflow_engine.py`

### Problemas conhecidos
- Nenhum. Todas as funcoes compilam e executam sem erros.

---

### Proximo Sprint — Sprint 5

**Modelo:** Claude Opus 4.8 (🔵) — continuamos
**Conteudo:** portfolio_analytics.py — VaR, Sharpe, Sortino, HHI, Duration + router

**Ficheiros a criar:**
- `app/services/portfolio_analytics.py`:
  - `calculate_all_metrics()` — orquestrador
  - `calc_var_historic()` / `calc_var_parametric()` / `calc_cvar()`
  - `calc_sharpe_ratio()` — Rf = BNA rate - IAC
  - `calc_sortino_ratio()` — downside deviation only
  - `calc_calmar_ratio()` / `calc_information_ratio()`
  - `calc_concentration_hhi()` / `calc_concentration_gini()` / `calc_effective_n()`
  - `calc_liquidity_score()` / `calc_drawdown()`
- Router: portfolio_analytics endpoints para GET/POST

Usa como fundacao:
- `app/services/financial_core.py` (YTM, duration, convexity, fisher)
- `app/services/tax_engine.py` (IAC rates)
- `app/models/portfolio.py` / `app/models/portfolio_holding.py`
- `app/models/portfolio_analytics.py` (para persistencia dos snapshots)
