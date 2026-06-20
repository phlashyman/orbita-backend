## Handoff — Sprint 5 concluido → Sprint 6

**Modelo:** Claude Opus 4.8 (🔵)
**Data:** 2026-06-20

---

### Sprint 4 + 5 — Motores Financeiros (Claude)

| Sprint | Ficheiros | Linhas |
|--------|-----------|--------|
| Sprint 4 | `financial_core.py` (319), `tax_engine.py` (117), `cashflow_engine.py` (245) | 681 |
| Sprint 5 | `portfolio_analytics.py` (563) | 563 |

**Todas as funcoes verificadas com 12+ testes cada.**

---

### RESUMO PARA O PROXIMO SPRINT

**Proximo:** Sprint 6 (DeepSeek 🟢)
**Conteudo:** investor_profile.py (questionario 2 modos) + router
**Sprint 7:** investment_strategies.py (Bullet/Barbell/Ladder/DCA)

**Fundacoes prontas que o DeepSeek vai usar:**
- `app/services/financial_core.py` — YTM, duration, fisher_real, solve_ytm, generate_cash_flows
- `app/services/tax_engine.py` — resolve_tax_rates(), get_active_iac_rate()
- `app/services/cashflow_engine.py` — bond_coupon_schedule(), portfolio_cashflows(), next_payment()
- `app/services/portfolio_analytics.py` — calculate_all_metrics(), todos os calcs puros
- `app/models/investor_profile.py` — modelo ja criado (Sprint 3)
- `app/schemas/investment.py` — schemas ja criados (Sprint 3)
- `app/routers/investment.py` — router base ja criado (Sprint 3)

**O Sprint 6 precisa de:**
1. Criar `app/services/investor_profile.py` — logica do questionario (6Q rapido / 10Q completo)
   - Scoring algorithm com pesos CFA
   - `_calculate_profile()` — ja existe logica no router
   - `generate_ips()` — placeholder para geracao PDF
2. Melhorar endpoint `/investor-profile/submit` — usar o novo service
3. Adicionar endpoint `/investor-profile/ips` — gerar IPS

**O Sprint 7 precisa de:**
1. Criar `app/services/investment_strategies.py`
   - `suggest_strategies()` — Bullet/Barbell/Ladder baseado no perfil
   - `bullet_vs_barbell_vs_ladder()` — comparador
   - `dca_vs_lump_sum_simulation()` — simulador DCA vs Lump Sum
2. Router `/strategies/` endpoints

**Problemas pendentes:**
1. PostgreSQL nao esta a correr localmente — migracoes Alembic nao executadas
2. .env tem chaves API vazias
3. GitHub repos criados e funcionais: https://github.com/phlashyman/orbita-backend e orbita-frontend

**Instrucoes para o Joao:**
1. `/model deepseek-chat` para mudar para DeepSeek
2. Dizer "Sprint 6" ao DeepSeek
3. O DeepSeek deve ler este HANDOFF.md primeiro
