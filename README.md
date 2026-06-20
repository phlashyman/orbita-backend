# Orbita Backend

Backend API da plataforma Orbita — inteligencia financeira para o mercado angolano (BODIVA).

## Stack Tecnologico

| Componente | Tecnologia |
|-----------|-----------|
| Framework | FastAPI (Python 3.11) |
| Base de Dados | PostgreSQL 15 |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Auth | JWT + bcrypt |
| Storage | MinIO S3-compatible |
| AI | Anthropic Claude API |
| Container | Docker + Docker Compose |

## Estrutura do Projeto

```
app/
├── main.py              # Entry point FastAPI
├── config.py            # Configuracao (pydantic-settings)
├── database.py          # Engine + session async
├── models/              # 8 tabelas SQLAlchemy
├── schemas/             # Schemas Pydantic v2
├── routers/             # 7 routers (30+ endpoints)
├── services/            # Logica de negocio
├── dependencies/        # Auth, db session
└── utils/               # Helpers, seed data
docs/
├── ORBITA_PROJECT_MASTER.md    # Documento mestre
└── ANEXO_DEPLOYMENT_ORBITA.md  # Estrategia de deployment
migrations/              # Alembic
```

## Documentacao

- [Documento Mestre da Solucao](docs/ORBITA_PROJECT_MASTER.md)
- [Estrategia de Deployment](docs/ANEXO_DEPLOYMENT_ORBITA.md)

## Como Correr Localmente

```bash
# 1. Copiar environment
cp .env.example .env
# Editar .env — adicionar ANTHROPIC_API_KEY

# 2. Iniciar containers
docker-compose up -d

# 3. Seed dados demo
docker-compose exec backend python -m app.utils.seed

# 4. API disponivel em http://localhost:8000
# Docs interactivos: http://localhost:8000/docs
```

## API Endpoints

| Router | Prefixo | Endpoints |
|--------|---------|-----------|
| Auth | `/auth` | register, login, me, family members |
| Bank Accounts | `/bank-accounts` | CRUD |
| Budget | `/budget` | categories + summary |
| Transactions | `/transactions` | CRUD + receipt upload |
| Statements | `/statements` | import, upload CSV/OFX |
| Conciliation | `/conciliation` | match, unmatch, auto-match |
| News | `/news` | public feed + admin + AI generation |

## Deployment

Ver [ANEXO_DEPLOYMENT_ORBITA.md](docs/ANEXO_DEPLOYMENT_ORBITA.md) para a estrategia completa (Fase 1: Railway free -> Fase 2: DigitalOcean VPS -> Fase 3: AWS).

## Autor

PulsarTec — joaoc.pulsartech@gmail.com
