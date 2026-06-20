## Handoff — Sprint 2 → Sprint 3

**De:** DeepSeek (🟢)
**Para:** DeepSeek (🟢) — continuamos
**Data:** 2026-06-20

---

### O que foi feito no Sprint 2

**Teste exaustivo de parsers contra ficheiros reais.**

Foram testados parsers dos 3 AIs (Claude, Kimi, Manu) contra 7 formatos de ficheiros em `Ficheiros de Uploads - Orbita/`:

| Formato | Ficheiro testado | Resultado |
|---------|-----------------|-----------|
| Aurea Carteira (.xlsx) | Carteira (10).xlsx | ✅ 7 holdings extraídas |
| Bolsa Destaques (.xlsx) | Bolsa-Destaques (1).xlsx | ✅ 20 instrumentos |
| Ordens Disponiveis (.xlsx) | Ordens_Disponiveis_04-05-2026_... | ✅ 166 rows, 400 order book entries |
| Resumo Mercados (.xlsx) | Resumo dos Mercados - 05-05-2026... | ✅ 24 instrumentos |
| Standard Carteira (.pdf) | Standard Gestao de Activos... | ✅ 3 posições, 799.682 AOA |
| Ficha Técnica (.pdf) | AOBAIAAAAA05-20260430.pdf | ✅ ISIN, ticker, issuer, class |
| Boletim BODIVA (.pdf) | boletimdiario20260514.pdf | ✅ 3 sub-parsers (OTC, leilão, eventos) |

### Decisão: Kimi vence para TODOS os formatos

Os parsers do Kimi (já no `orbita-backend/app/services/ingestion/`) são superiores em todos os 7 formatos.

**Contribuições a incorporar dos outros AIs:**
1. **Tolerância multi-coluna** (Manu) — adicionar fallbacks de nomes de coluna com/sem acentos
2. **FISN cross-validation** (Claude) — validação de datas via ISO 18774 para fichas técnicas

### Ficheiros usados nos testes (não modificar)
- `C:\Users\jotac\OneDrive\Documents\GitHub\Projecto Orbita\Ficheiros de Uploads - Orbita/` — ficheiros originais, apenas leitura

### Próximos passos — Sprint 3

**Modelo:** DeepSeek (🟢)
**Conteúdo:** Portar 17 models base do Kimi + criar 12 novos models de investimento + Auth + Config + DB + migrações Alembic

**Ficheiros a criar/modificar:**
- `app/models/` — (já existem do Kimi, verificar se estão completos)
- `app/models/investor_profile.py` — NOVO (perfil psicométrico)
- `app/models/portfolio_analytics.py` — NOVO (snapshot de métricas)
- `app/models/scenario_analysis.py` — NOVO (unifica stress test + monte carlo)
- `app/models/scenario_definition.py` — NOVO (cenários macro)
- `app/models/investment_signal.py` — NOVO (unifica estratégia + swap + sinal)
- `app/models/investment_goal.py` — NOVO (objectivos financeiros)
- `app/models/ai_assistant_log.py` — NOVO (log interacções AI)
- `app/models/educational_content_view.py` — NOVO (tracking academy)
- `app/models/currency_pair.py` — NOVO (taxas de câmbio)
- `app/models/international_position.py` — NOVO (posições internacionais)
- `app/models/market_comparison.py` — NOVO (comparação histórica)
- `app/models/country_risk_metric.py` — NOVO (CRP, rating, CDS)
- `app/routers/__init__.py` — actualizar imports
- `app/main.py` — adicionar novos routers
- Migrações Alembic para novos models

### Notas importantes
1. `gh` CLI não está disponível — GitHub remotes não configurados
2. `.env` tem chaves API vazias (ANTHROPIC_API_KEY, SERPAPI_KEY)
3. Detecção de parsers funciona com scores > 0.9 para todos os formatos
