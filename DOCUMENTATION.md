# Orbita — Documentacao Tecnica Completa

> **Projecto:** Orbita — Plataforma de Inteligencia Financeira (BODIVA)
> **Empresa:** PulsarTec
> **Versao:** 1.0.0 (MVP)
> **Data:** 22 Junho 2026
> **Ultimo deploy:** Railway + Vercel (CI/CD automatico via GitHub Actions)

---

## 1. Visao Geral

A Orbita e uma plataforma de inteligencia financeira para o mercado de capitais angolano (BODIVA — Bolsa de Divida e Valores de Angola). Oferece gestao de portfolio, analise de risco, inteligencia de mercado via IA, e acesso a mercados internacionais.

### Caracteristicas Principais

- **Gestao de Portfolio:** Consolidacao multi-broker, calculo de YTM/Duration/Convexity, cashflows projectados
- **Analise de Risco:** VaR, CVaR, Sharpe, Sortino, stress tests, Monte Carlo
- **Market Intelligence:** 8 detectores deterministicos de sinais de mercado
- **Motor de Swap:** Analise de troca de titulos com beneficio liquido apos comissoes + IAC + mais-valias
- **AI Integration:** Noticias, analises, portfolio builder via Anthropic Claude API
- **Mercados Internacionais:** Markowitz, Kelly Criterion, comparador historico, currency risk
- **Personal Finance:** Orcamento familiar, reconciliacao bancaria, objectivos financeiros
- **Perfil de Investidor:** Questionario psicometrico (CFA-aligned), IPS generator
- **Financas Pessoais:** Orcamento, reconciliacao bancaria, gestao de patrimonio

---

## 2. Infraestrutura

| Componente | Servico | URL |
|-----------|---------|-----|
| **Backend API** | Railway | `orbita-backend-production-e106.up.railway.app` |
| **Base de Dados** | Railway PostgreSQL | Managed (17.00%, porta 5432) |
| **Frontend SPA** | Vercel | `orbita.pulsartech.pt` (dominio principal) |
| **DNS** | Cloudflare | `pulsartech.pt` — CNAME `orbita` → Vercel |
| **Storage** | Cloudflare R2 (planeado) | 10GB free tier, S3-compatible |
| **CI/CD** | GitHub Actions | Test + Deploy automatico em cada push para `main` |
| **Error Tracking** | Sentry (opcional) | DSN via env var `SENTRY_DSN` |

### Custos Mensais Estimados (Producao)

| Servico | Plano | Custo |
|---------|-------|-------|
| Railway (Backend + PostgreSQL) | Hobby | ~$5/mes |
| Vercel (Frontend) | Free | $0 |
| Cloudflare (DNS + CDN) | Free | $0 |
| **Total** | | **~$5/mes** |

---

## 3. Stack Tecnologica

### Backend (Python 3.11)
- **Framework:** FastAPI (uvicorn)
- **ORM:** SQLAlchemy 2.0 (async + asyncpg)
- **Migracoes:** Alembic
- **Auth:** JWT (python-jose) + bcrypt (passlib) + RBAC (ADMIN / GESTOR / MEMBER)
- **Containerizacao:** Docker + Docker Compose
- **Dependencias Chave:** httpx, openpyxl, pdfplumber, pypdf, pydantic v2

### Frontend (TypeScript 5.9)
- **Framework:** React 19
- **Build:** Vite 7
- **Styling:** Tailwind CSS 3 + shadcn/ui (~50 componentes)
- **Charts:** Recharts
- **Animacoes:** Framer Motion, GSAP
- **Routing:** React Router 7 (HashRouter)
- **HTTP:** Axios com JWT interceptor

### Ambiente de Desenvolvimento
```bash
# Backend
cd orbita-backend
docker compose up -d          # PostgreSQL + MinIO + Backend (port 8000)
# Health check: curl http://localhost:8000/health

# Frontend
cd orbita-frontend
npm install
npm run dev                   # Vite dev server (port 3000)
npm run build                 # Build producao → dist/
```

---

## 4. Arquitectura do Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (React + Vite)                   │
│  23 paginas · HashRouter · AuthContext · 15 API modules      │
│  orbita.pulsartech.pt                                       │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS (Axios + JWT Bearer)
                       │ CORS: settings.cors_origins
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                         │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ 14       │  │ 10       │  │ 22       │  │ 30       │   │
│  │ Routers  │  │ Schemas  │  │ Services │  │ Models    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                              │
│  Auth (JWT) · CORS · Security Headers · Rate Limiting       │
│  orbita-backend-production-e106.up.railway.app              │
└──────────────────────┬──────────────────────────────────────┘
                       │ asyncpg
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              PostgreSQL 15 (Railway Managed)                 │
│  36 tabelas + enums + indices                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Modelos de Dados (36 Tabelas)

### 5.1 Modelos Base (Kimi AI — portados)
| Modelo | Tabela | Descricao |
|--------|--------|-----------|
| `Family` | `families` | Multi-tenant root scoping |
| `User` | `users` | 3 roles: ADMIN, GESTOR, MEMBER |
| `BankAccount` | `bank_accounts` | Contas bancarias por family |
| `BudgetCategory` | `budget_categories` | Categorias de orcamento |
| `TransactionManual` | `transactions_manual` | Transaccoes manuais + recibos |
| `BankStatement` | `bank_statements` | Extractos bancarios |
| `ConciliationLog` | `conciliation_log` | Matching transaccoes ↔ extractos |
| `MarketNews` | `market_news` | Noticias AI (DRAFT/PENDING/PUBLISHED/REJECTED) |
| `Broker` | `brokers` | Corretoras BODIVA |
| `Instrument` | `instruments` | Instrumentos negociados |
| `Portfolio` | `portfolios` | Carteiras (REAL/SIMULATED) |
| `PortfolioHolding` | `portfolio_holdings` | Posicoes dentro de carteiras |
| `Trade` | `trades` | Transaccoes BUY/SELL/COUPON/MATURITY |
| `BrokerFileUpload` | `broker_file_uploads` | Uploads de ficheiros de corretora |
| `WatchlistItem` | `watchlist_items` | Watchlist internacional |

### 5.2 Modelos BODIVA (market data)
| Modelo | Tabela | Descricao |
|--------|--------|-----------|
| `MarketSnapshot` | `market_snapshots` | Snapshots diarios do mercado |
| `OrderBookSnapshot` | `order_book_snapshots` | Profundidade do order book |
| `BondMaster` | `bond_master` | Dados de referencia de bonds |
| `ImportLog` | `import_log` | Log de idempotencia de imports |
| `YieldCurveHistory` | `yield_curve_history` | Historico da curva de juros |
| `IncomeEvent` | `income_events` | Eventos de rendimento |
| `BodivaMonthlyAggregate` | `bodiva_monthly_aggregates` | Agregados mensais |
| `BodivaQuarterlyAggregate` | `bodiva_quarterly_aggregates` | Agregados trimestrais |

### 5.3 Modelos de Investimento (Sprint 3 — novos)
| Modelo | Tabela | Descricao |
|--------|--------|-----------|
| `InvestorProfile` | `investor_profiles` | Perfil psicometrico CFA-aligned |
| `PortfolioAnalytics` | `portfolio_analytics` | Snapshots de metricas (VaR, Sharpe, HHI...) |
| `ScenarioAnalysis` | `scenario_analyses` | Stress tests + Monte Carlo |
| `ScenarioDefinition` | `scenario_definitions` | Cenarios macro (Angola) |
| `InvestmentSignal` | `investment_signals` | Alertas/recomendacoes/swaps |
| `InvestmentGoal` | `investment_goals` | Objectivos financeiros |
| `AIAssistantLog` | `ai_assistant_logs` | Log de custos AI + auditoria |
| `EducationalContentView` | `educational_content_views` | Tracking Orbita Academy |
| `CurrencyPair` | `currency_pairs` | Taxas USD/AOA, EUR/AOA, ZAR/AOA |
| `InternationalPosition` | `international_positions` | Posicoes internacionais |
| `MarketComparison` | `market_comparisons` | Comparador historico |
| `CountryRiskMetric` | `country_risk_metrics` | CRP Damodaran, rating, CDS |
| `TaxRule` | `tax_rules` | IAC temporal (Lei 14/25) |

---

## 6. Routers (14 Ficheiros, ~157 Endpoints)

| Router | Prefixo | Endpoints | Acesso |
|--------|---------|-----------|--------|
| `auth.py` | `/auth` | register, login, me, bootstrap-admin, promote-first-admin, reset-all-users, family/members CRUD, users (admin) | Publico + Autenticado + Admin |
| `bank_accounts.py` | `/bank-accounts` | CRUD | Autenticado |
| `budget.py` | `/budget` | Categorias + monthly summary | Autenticado |
| `transactions.py` | `/transactions` | CRUD + receipt upload | Autenticado |
| `statements.py` | `/statements` | Import + lines | Autenticado |
| `conciliation.py` | `/conciliation` | Match, unmatch, auto-match, status | Autenticado |
| `news.py` | `/news` | Public feed, search, admin CRUD, AI generation, diag, stats | Publico + Admin |
| `portfolio.py` | `/portfolio` | Portfolios, holdings, instruments, brokers, trades, summaries | Autenticado |
| `broker_files.py` | `/portfolio/uploads` | Upload, detect, preview, process, import | Autenticado + Admin |
| `market_data.py` | `/market-data` | BODIVA instruments/orderbook/yield-curve + SerpAPI global indices/currencies/quotes | Publico |
| `watchlist.py` | `/watchlist` | CRUD | Autenticado |
| `investment.py` | (multiplos) | 6 sub-routers: `/investor-profile`, `/goals`, `/strategies`, `/scenarios`, `/signals`, `/international`, `/ai`, `/academy`, `/tax-rules` | Autenticado + Admin |

---

## 7. Servicos (22 Ficheiros)

### 7.1 Motores Financeiros (Claude AI)
| Servico | Funcoes Chave |
|---------|---------------|
| `financial_core.py` | `solve_ytm()` (Newton-Raphson Decimal 28), `calc_duration()`, `fisher_real()`, `calc_liquidation()`, `generate_cash_flows()` |
| `tax_engine.py` | `resolve_tax_rates()` (IAC temporal), `resolve_for_bond()`, `get_active_iac_rate()` |
| `cashflow_engine.py` | `bond_coupon_schedule()`, `portfolio_cashflows()`, `next_payment()`, `monthly_cashflow_table()` |
| `portfolio_analytics.py` | VaR (parametrico + historico), CVaR, Sharpe, Sortino, Calmar, HHI, Gini, Liquidez, Drawdown |
| `plan_engine.py` | `swap_benefit()`, `buy_window()`, `find_swaps()`, `evaluate_plan()` — 42 testes originais |
| `market_intelligence.py` | 8 detectores deterministicos de sinais de mercado |
| `risk_manager.py` | 4 cenarios Angola, stress tests, early warnings (7 regras), liquidity, concentration |
| `scenario_engine.py` | Monte Carlo (1K paths), multi-factor, sensitivity matrix, tornado chart |

### 7.2 Investimento & AI
| Servico | Funcoes Chave |
|---------|---------------|
| `international_markets.py` | Markowitz, Kelly Criterion, currency risk, comparador historico, alocacao internacional |
| `investment_strategies.py` | Bullet/Barbell/Ladder, DCA vs Lump Sum |
| `investor_profile.py` | Questionario 6Q/10Q CFA-aligned, IPS generator |
| `investment_education.py` | Glossario (20 termos), tooltips (15 metricas), calculadoras |
| `ai_assistant.py` | Cost controls (tiering Haiku/Sonnet, daily cap $5), audit logging, templates |
| `ai_news.py` | Geracao de noticias via Anthropic API com contexto macro actualizado |

### 7.3 Pipeline & Infraestrutura
| Servico | Descricao |
|---------|-----------|
| `ingestion/` (8 ficheiros) | Deteccao, parsers Excel/PDF, persistencia SQLAlchemy |
| `market_data.py` | SerpAPI proxy com cache 10min |
| `scheduler.py` | 5 jobs automaticos (APScheduler) |
| `broker_file_parser.py` | Legacy CSV/XLSX/TXT parser |
| `receipt_pipeline.py` | Processamento de comprovantes |
| `statement_parser.py` | Parser de extractos bancarios |
| `conciliation.py` + `auto_matcher.py` | Matching algoritmo de reconciliacao |

---

## 8. Frontend (23 Paginas)

### 8.1 Paginas Publicas
| Pagina | Rota | Descricao |
|--------|------|-----------|
| `Home.tsx` | `/` | Landing page com hero, features, gallery |
| `Login.tsx` | `/login` | Login form (OAuth2 Password) |
| `Register.tsx` | `/registar` | Registo de novo family + Gestor |
| `Recover.tsx` | `/recuperar` | Recuperacao de password |
| `About.tsx` | `/sobre` | Sobre a PulsarTec |

### 8.2 Paginas Autenticadas (Core)
| Pagina | Rota | Descricao |
|--------|------|-----------|
| `Dashboard.tsx` | `/dashboard` | KPI cards, wealth chart, alerts, market snapshot |
| `Portfolio.tsx` | `/portfolio` | Holdings, cashflows, import broker files |
| `MarketWatch.tsx` | `/mercado` | BODIVA: instruments, order book, yield curve, signals |
| `GlobalMarkets.tsx` | `/mercados-globais` | SerpAPI: indices, currencies, movers, watchlist |
| `Simulations.tsx` | `/simulacoes` | Investment simulations |
| `AIBuilder.tsx` | `/ai-builder` | AI portfolio builder |

### 8.3 Paginas Autenticadas (Gestao)
| Pagina | Rota | Descricao |
|--------|------|-----------|
| `Budget.tsx` | `/orcamento` | Orcamento familiar |
| `Reconciliation.tsx` | `/reconciliacao` | Conciliacao bancaria |
| `Patrimony.tsx` | `/patrimonio` | Net worth tracking |
| `Planning.tsx` | `/planeamento` | Financial planning |
| `Documents.tsx` | `/documentos` | Document management |
| `Reports.tsx` | `/relatorios` | Report generation |
| `Settings.tsx` | `/configuracoes` | User settings |
| `News.tsx` | `/noticias` | Public news feed |

### 8.4 Paginas de Investimento (Novas — Sprint 12-13)
| Pagina | Rota | Descricao |
|--------|------|-----------|
| `InvestorProfile.tsx` | `/perfil-investidor` | Questionario psicometrico + IPS |
| `Strategies.tsx` | `/estrategias` | Bullet/Barbell/Ladder/DCA comparison |
| `Academy.tsx` | `/academy` | Glossario pesquisavel com explicacoes |

### 8.5 Admin
| Pagina | Rota | Descricao |
|--------|------|-----------|
| `Admin.tsx` | `/admin` | Users, uploads, news generation, BODIVA data, instruments, tax rules |

### Componentes Partilhados
| Componente | Funcao |
|-----------|--------|
| `Layout.tsx` | Layout principal |
| `Navbar.tsx` | Navegacao com dropdowns |
| `Footer.tsx` | Footer com disclaimer |
| `ProtectedRoute.tsx` | Guard de autenticacao + RBAC |
| `AuthLayout.tsx` | Layout para paginas de auth |
| `DataFetchWrapper.tsx` | Loading/Empty/Error states |
| `MetricCard.tsx` | KPI card com tooltip |
| `BrokerFileUpload.tsx` | Upload de ficheiros de corretora |

### API Modules (15 ficheiros)
`client.ts`, `auth.ts`, `bankAccounts.ts`, `bodivaMarket.ts`, `brokerFiles.ts`, `budget.ts`, `conciliation.ts`, `index.ts`, `investment.ts`, `marketData.ts`, `news.ts`, `portfolio.ts`, `statements.ts`, `transactions.ts`, `watchlist.ts`

---

## 9. Variaveis de Ambiente (Railway)

| Variavel | Obrigatoria | Descricao |
|----------|------------|-----------|
| `DATABASE_URL` | ✅ | Injectada automaticamente pelo Railway PostgreSQL |
| `SECRET_KEY` | ✅ | 64 chars aleatorios para assinar JWT |
| `ANTHROPIC_API_KEY` | ✅ | Chave da API Anthropic (sk-ant-api03-...) |
| `SERPAPI_KEY` | Recomendado | Chave da SerpAPI para mercados globais |
| `CORS_ORIGINS` | ✅ | `https://orbita.pulsartech.pt` |
| `RAILWAY_ENVIRONMENT` | ✅ | `production` |
| `S3_ENDPOINT` | Opcional | Cloudflare R2 endpoint |
| `S3_ACCESS_KEY` | Opcional | R2 Access Key |
| `S3_SECRET_KEY` | Opcional | R2 Secret Key |
| `S3_BUCKET` | Opcional | `orbita-uploads` |
| `SENTRY_DSN` | Opcional | Sentry error tracking |
| `AI_DAILY_CAP_USD` | Opcional | Limite diario de custos AI (default $5) |

---

## 10. Workflows GitHub Actions

### `.github/workflows/test.yml`
- Trigger: push/PR para `main`, `staging`
- Executa: pytest com cobertura + compile check

### `.github/workflows/deploy.yml`
- Trigger: push para `main`
- Faz deploy do backend no Railway via CLI

### `.github/workflows/backup.yml`
- Trigger: schedule diario (03:00 UTC)
- Executa: `pg_dump` para Cloudflare R2

---

## 11. Seguranca

- **JWT:** HS256, 60 min expiry, `secret_key` obrigatoria
- **Passwords:** bcrypt (passlib) — nunca em plain text
- **RBAC:** 3 roles (ADMIN / GESTOR / MEMBER), decorators `require_admin`, `require_gestor`
- **CORS:** Restrito ao dominio de producao
- **Security Headers:** X-Content-Type-Options, X-Frame-Options, HSTS, Referrer-Policy
- **Rate Limiting:** slowapi (200 req/min, opcional)
- **Soft Delete:** `deleted_at` timestamp em todos os modelos BaseMixin
- **API Keys:** Nunca hardcoded. Lidas de env vars com fallback a `/etc/secrets/` no Railway
- **Bootstrap Admin:** `POST /auth/bootstrap-admin` so funciona com BD vazia
- **Promote First Admin:** `POST /auth/promote-first-admin` so funciona sem admins existentes
- **Reset Users:** `DELETE /auth/reset-all-users` so funciona sem admins existentes

---

## 12. Processo de Deploy

1. **Git Push** → `git push origin main`
2. **GitHub Actions** → testes + deploy automatico
3. **Railway** → detecta push, faz build Docker, deploy (~2 min)
4. **Vercel** → detecta push, `npm run build`, deploy (~1 min)

### Health Check
- `GET /health` → `{"status":"ok"}` (instantaneo, sem DB)
- `GET /health/full` → verifica DB + AI key + SerpAPI key
- `GET /health/db` → diagnostico da conexao PostgreSQL
- `GET /news/admin/diag` → diagnostico da conexao Anthropic API

### Rollback
```bash
git revert HEAD
git push origin main  # Redeploy automatico
```

---

## 13. Fluxo de Primeiro Setup (Railway)

1. Criar projecto `orbita` no Railway
2. Adicionar servico PostgreSQL → `DATABASE_URL` injectado automaticamente
3. Adicionar servico backend (import GitHub `orbita-backend`) → detecta Dockerfile
4. Adicionar variaveis de ambiente (ver Seccao 9)
5. Redeploy → backend arranca, `create_all()` cria 36 tabelas
6. `POST /auth/bootstrap-admin` para criar primeiro admin
7. Deploy frontend na Vercel (import `orbita-frontend`)
8. Configurar `VITE_API_BASE_URL` na Vercel com o dominio Railway
9. Configurar DNS Cloudflare: `CNAME orbita → cname.vercel-dns.com`
10. Adicionar `CORS_ORIGINS` no Railway

---

## 14. Testes (80 unitarios + integracao)

- `tests/test_financial_core.py` — 26 testes (YTM, Duration, Liquidation, Fisher)
- `tests/test_portfolio_analytics.py` — 29 testes (VaR, CVaR, HHI, Gini, Sharpe, Drawdown)
- `tests/test_integration.py` — 25 testes (cross-module, swap, signals, early warnings)

```bash
cd orbita-backend
python -m pytest tests/ -v
# 80 passed
```

---

## 15. Troubleshooting Comum

### "Network Error" no frontend
1. Verificar `VITE_API_BASE_URL` na Vercel aponta para o dominio Railway correcto
2. Verificar `CORS_ORIGINS` no Railway inclui o dominio do frontend
3. F12 → Console → verificar URL do pedido que falhou

### "401 Unauthorized" no login
1. Fazer registo primeiro em `/registar`
2. Verificar `SECRET_KEY` no Railway

### Noticias nao aparecem
1. Verificar `ANTHROPIC_API_KEY` no Railway → `GET /news/admin/diag`
2. Apenas artigos com status `PUBLISHED` aparecem no feed publico
3. Artigos em `PENDING_REVIEW` precisam de ser aprovados pelo admin

### Timeout ao gerar noticias
1. O endpoint gera 1 artigo por chamada (~10-15s)
2. O frontend faz loop se precisar de varios artigos
3. Timeout maximo: 120s no client, ~15s por artigo no backend

### "relation does not exist"
1. As tabelas sao criadas automaticamente no arranque (`create_all()`)
2. Se uma tabela nao existe, fazer redeploy do backend

---

## 16. Repositorios GitHub

| Repo | URL |
|------|-----|
| Backend | https://github.com/phlashyman/orbita-backend |
| Frontend | https://github.com/phlashyman/orbita-frontend |

---

## 17. Glossario de Dominio (Angola/BODIVA)

| Termo | Significado |
|-------|------------|
| **BODIVA** | Bolsa de Divida e Valores de Angola |
| **OT** | Obrigacao do Tesouro (sovereign bond) |
| **OT-NR** | OT a taxa nominal referenciada (floating rate) |
| **OT-TX** | OT a taxa fixa |
| **OT-ME** | OT em moeda estrangeira (USD) |
| **BT** | Bilhete do Tesouro (T-bill, curto prazo) |
| **BNA** | Banco Nacional de Angola (banco central) |
| **TBC** | Taxa Basica de Juro do BNA (benchmark rate) |
| **IAC** | Imposto sobre Aplicacao de Capitais (10% desde Lei 14/25) |
| **UGD** | Unidade de Gestao da Divida Publica |
| **INE** | Instituto Nacional de Estatistica |
| **Kwanza (AOA)** | Moeda nacional de Angola |

---

*Documento gerado automaticamente a partir do codigo-fonte do projecto Orbita.*
*Ultima actualizacao: 22 Junho 2026*
