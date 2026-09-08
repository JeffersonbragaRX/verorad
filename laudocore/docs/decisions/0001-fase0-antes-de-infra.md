# ADR 0001 — Fase 0 isolada, sem ingestão/DB/UI ainda

**Status:** aceito

## Contexto

A especificação mestra (`ESPECIFICACAO_MESTRA_LAUDOCORE_WORK.md`, seção 33)
define como "primeira entrega obrigatória" um conjunto que mistura
auditoria de corpus com ingestão, persistência em banco, separação de
seções/frases e um explorador local — tudo antes de qualquer IA
generativa. Isso é mais amplo que a "Fase 0" que a própria especificação
define na seção 32 (auditoria estrutural, estatísticas recalculadas,
qualidade, anomalias, relatório).

## Decisão

Entregar exatamente o escopo da seção 32 (Fase 0) nesta rodada: leitura
completa do corpus RAW recebido, recontagem independente de tudo que o
export de origem já declarava, detecção de anomalias, e os artefatos
`BASELINE_REPORT.md` / `QA_REPORT.json` / `exam_types.csv` /
`physicians.csv`. Ingestão em banco, parser de seções/sentenças e
explorador local ficam para a Fase 1, e apenas depois de decidido o
vertical inicial (ver `architecture.md`).

## Consequência

Nenhuma dependência nova foi instalada (script usa apenas a stdlib do
Python). O critério de aceite da Fase 0 ("100% das linhas lidas ou
justificadas como inválidas; contagens reprodutíveis") é verificado por
teste automatizado (`tests/test_baseline_audit.py`), incluindo uma
verificação de que duas execuções produzem o mesmo resultado.
