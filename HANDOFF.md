## Handoff — Sprints 6+7 concluidos → Sprint 8

**Modelo:** DeepSeek (🟢)
**Proximo:** Claude Opus 4.8 (🔵) — Sprint 8: risk_manager + scenario_engine
**Data:** 2026-06-20

---

### O que foi feito

**Sprint 6 — `app/services/investor_profile.py` (DeepSeek)**
- `get_quiz_questions()` — 6 perguntas rapido / 10 completo
- `calculate_profile()` — scoring com pesos CFA
- `generate_ips_text()` — IPS markdown com 7 seccoes
- 4 perfis com alocacao internacional (20-65%)
- Endpoints: /questions, /submit, /my-profile, /ips

**Sprint 7 — `app/services/investment_strategies.py` (DeepSeek)**
- `suggest_strategies()` — scoring por perfil + curva + volatilidade
- `compare_strategies()` — Bullet vs Barbell vs Ladder vs Riding Curve
- `simulate_dca_vs_lump_sum()` — DCA mensal vs lump sum
- Endpoints: /descriptions, /suggest, /compare, /dca-vs-lump

### Proximo Sprint — Sprint 8 (Claude 🔵)

**Ficheiros a criar:**
1. `app/services/risk_manager.py`:
   - `calc_var_historic()`, `calc_var_parametric()` — ja existe em portfolio_analytics, reutilizar
   - `stress_test()` — aplicar cenario macro ao portfolio
   - `run_scenario_analysis()` — correr todos os cenarios predefinidos
   - `generate_early_warnings()` — verificar regras contra metricas actuais
   - `liquidity_analysis()` — profundidade bid/ask, tempo liquidacao
   - `concentration_report()` — HHI, Gini, breakdown por issuer/class/maturidade

2. `app/services/scenario_engine.py`:
   - `monte_carlo_simulation(n_paths=1000)` — simplicado (sem GARCH)
   - `define_scenario(name, params)` — cenario personalizado
   - `prebuilt_scenarios()` — 4 cenarios Angola-specific
   - `sensitivity_matrix()` — impacto de variacoes de YTM
   - `tornado_chart_data()` — factores mais impactantes

**Problemas pendentes:**
1. PostgreSQL nao corre localmente — Docker Desktop precisa de estar activo
2. .env com chaves vazias (ANTHROPIC_API_KEY, SERPAPI_KEY)
3. GitHub: https://github.com/phlashyman/orbita-backend (8 commits)
