# ADR 0004 — SQLite como persistência local na Fase 1 (não PostgreSQL ainda)

**Status:** aceito, reversível

## Contexto

A especificação mestra define PostgreSQL + pgvector como stack alvo
(seção 5). Neste estágio (Fase 1, vertical único, ~900 registros, sem
retrieval vetorial ainda), subir e manter um servidor PostgreSQL não
adiciona valor proporcional ao esforço de configuração/infra.

## Decisão

Usar SQLite (`data/processed/laudocore.db`, fora do Git — ver ADR 0002)
para as tabelas `reports`, `report_sections` e `sentences` nesta fase.
O modelo relacional implementado (`backend/db/schema.py`) já segue o
schema conceitual da especificação (seção 7), então a migração futura
para PostgreSQL é mecânica (mesmas tabelas, mesmos tipos, troca do
driver). `pgvector` só entra quando a Fase 5 (retrieval híbrido)
justificar a necessidade de embeddings persistidos.

## Idempotência nesta fase

O script `scripts/ingest_vertical.py` recria o schema do zero
(`DROP TABLE IF EXISTS` + `CREATE TABLE`) a cada execução, em vez de
fazer upsert incremental. No volume atual (~900 registros, ingestão
completa em poucos segundos) isso é mais simples e igualmente
idempotente. Precisa ser revisto antes da Fase 9 (personalização), que
anexará correções/preferências a linhas específicas — nesse ponto,
recriar tudo do zero destruiria anotações humanas, e será necessário
upsert por `record_id`.
