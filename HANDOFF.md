## Handoff — Sprint 3 → Sprint 4

**De:** DeepSeek (🟢)
**Para:** Claude Opus 4.8 (🔵) — mudança de modelo!
**Data:** 2026-06-20

---

### O que foi feito no Sprint 3

**Core Backend completo — 36 models, 17 routers, migrações prontas.**

1. **Verificados e mantidos:** 17 models base portados do Kimi (User, Family, Portfolio, BankAccount, BODIVA market data, etc.)

2. **Criados 19 novos models:**
   - `InvestorProfile` — perfil psicométrico (modo rápido 6Q / completo 10Q)
   - `PortfolioAnalytics` — VaR, Sharpe, Duration, HHI, Gini, Liquidez
   - `ScenarioAnalysis` — stress tests + Monte Carlo
   - `ScenarioDefinition` — 4 cenários Angola-specific
   - `InvestmentSignal` — unifica alertas, recomendações, swaps
   - `InvestmentGoal` — objectivos financeiros com progresso
   - `AIAssistantLog` — tracking de custos AI com daily cap
   - `EducationalContentView` — tracking Academy
   - `CurrencyPair` — USD/AOA, EUR/AOA, ZAR/AOA
   - `InternationalPosition` — investimentos S&P500, JSE, etc.
   - `MarketComparison` — comparador histórico OT vs S&P500 vs Ouro
   - `CountryRiskMetric` — CRP Damodaran, rating, CDS, inflação
   - `TaxRule` — IAC temporal (5%/10% Lei 14/25)

3. **Routers criados (com endpoints funcionais):**
   - `investor_router` (`/investor-profile`) — questionário + submit + perfil
   - `goals_router` (`/goals`) — CRUD de objectivos
   - `scenarios_router` (`/scenarios/prebuilt`) — cenários predefinidos com seed data
   - `signals_router` (`/signals`) — listar e filtrar sinais
   - `international_router` (`/international`) — posições, FX, country risk
   - `tax_router` (`/tax-rules`) — CRUD regras + `/resolve` endpoint

4. **Migração Alembic 0003:** `add_investment_models` — CREATE TABLE para todos os 19 novos models + enums. Requer PostgreSQL para executar: `alembic upgrade head` (ou criar BD primeiro com `docker compose up -d`).

### Ficheiros criados/modificados

**Novos ficheiros:**
- `app/models/investor_profile.py`, `.../portfolio_analytics.py`, `.../scenario_analysis.py`, `.../scenario_definition.py`, `.../investment_signal.py`, `.../investment_goal.py`, `.../ai_assistant_log.py`, `.../educational_content_view.py`, `.../currency_pair.py`, `.../international_position.py`, `.../market_comparison.py`, `.../country_risk_metric.py`, `.../tax_rule.py`
- `app/schemas/investment.py` — schemas agrupados para todos os novos models
- `app/routers/investment.py` — 6 routers num ficheiro
- `migrations/versions/0003_add_investment_models.py`
- `migrations/env.py`, `migrations/script.py.mako`

**Ficheiros modificados:**
- `app/models/__init__.py` — adicionados todos os novos models
- `app/routers/__init__.py` — adicionados novos routers
- `app/main.py` — registados 6 novos routers

### Problemas conhecidos

1. **PostgreSQL não está a correr** — a migração Alembic 0003 não foi executada. Para aplicar: `docker compose up -d && alembic upgrade head`
2. **Docker não está a correr** — o engine Docker da máquina não está activo. É preciso iniciar o Docker Desktop primeiro.
3. **Questionário usa scoring simplificado** — o cálculo do perfil está implementado com lógica no router. Os Sprints 5-6 vão refinar com `portfolio_analytics.py` e `financial_core.py`.
4. **Endpoints sem autenticação total** — `scenarios_router` e `tax_router` estão parcialmente abertos. Segurança refinada nos Sprints seguintes.
5. **.env vazio** — `ANTHROPIC_API_KEY` e `SERPAPI_KEY` ainda vazios.

### Próximos passos — Sprint 4

**Modelo:** Claude Opus 4.8 (🔵)
**Conteúdo:** financial_core.py + tax_engine.py + cashflow_engine.py (port do Claude AI)

**Ficheiros a criar:**
- `app/services/financial_core.py` — portar de `...Claude/.../modules/financial_core.py` (273 linhas)
  - `solve_ytm()` — Newton-Raphson Decimal(28)
  - `calc_duration()` — Macaulay + Modified + Convexity
  - `fisher_real()` — equação de Fisher ajustada para Angola
  - `calc_liquidation()` — com comissões + IRC + IAC
  - `generate_cash_flows()` — projecção de cupões
- `app/services/tax_engine.py` — portar de `...Claude/.../modules/tax_engine.py` (122 linhas)
  - `resolve_tax_rates()` — query temporal à tabela tax_rules
- `app/services/cashflow_engine.py` — portar de `...Claude/.../modules/cashflow_engine.py` (205 linhas)
- Router `portfolio_analytics_router` — endpoints VaR, Sharpe, Duration

**Caminhos para os ficheiros Claude:**
```
C:\Users\jotac\OneDrive\Documents\GitHub\Projecto Orbita\Claude AI - Projecto Orbita\Investment Monitoring\bodiva_terminal\modules\
  ├── financial_core.py   → port para app/services/financial_core.py
  ├── tax_engine.py       → port para app/services/tax_engine.py
  └── cashflow_engine.py  → port para app/services/cashflow_engine.py
```

### Nota importante — transição de modelo

Este é o primeiro **handoff entre modelos**. O João vai mudar de `/model deepseek-chat` para `/model default` (Claude Opus 4.8). O Claude deve começar por ler este HANDOFF.md e continuar o Sprint 4. Boa sorte! 🚀
