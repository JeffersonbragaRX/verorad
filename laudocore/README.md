# LaudoCore (provisório)

Laudador inteligente geral de Radiologia e Diagnóstico por Imagem —
escopo inicial RM, TC e RX, arquitetura baseada em corpus real +
conhecimento médico canônico + perfil de redação por médico + retrieval
híbrido + regras determinísticas + auditoria clínica + LLM controlado
(nunca a fonte única de verdade clínica).

Este diretório vive dentro do repositório `verorad`, que também contém
um produto não relacionado (estimador de idade óssea). Ver
`docs/decisions/0003-local-do-repositorio.md` para o porquê e como
migrar para um repositório dedicado se desejado.

## Estado atual: Fase 0 concluída

Auditoria estrutural do corpus recebido (`TCRMRX.zip`, export CMS,
janela 2026-06-06 a 2026-09-06, RM+TC+RX — US ainda pendente de
exportação). Nenhuma linha do corpus foi descartada silenciosamente;
toda estatística foi recalculada de forma independente a partir do
JSONL bruto e cruzada contra os números que o próprio export já trazia.

Entregáveis:

- [`docs/BASELINE_REPORT.md`](docs/BASELINE_REPORT.md) — relatório legível
- [`data/derived/qa/QA_REPORT.json`](data/derived/qa/QA_REPORT.json) — auditoria estruturada completa
- [`data/derived/qa/exam_types.csv`](data/derived/qa/exam_types.csv) — 210 exam_type distintos
- [`data/derived/qa/physicians.csv`](data/derived/qa/physicians.csv) — 7 médicos
- [`docs/data_dictionary.md`](docs/data_dictionary.md) — schema real observado
- [`docs/architecture.md`](docs/architecture.md) — estado da arquitetura
- `docs/decisions/` — decisões registradas (ADRs)

## Reproduzir

```bash
# 1. Colocar o corpus (fora do git) em:
#    data/raw/CMS_CORPUS_2026-06-06_A_2026-09-06/<snapshot>/{manifest,stats}.json + reports_*.jsonl

python3 scripts/baseline_audit.py
python3 -m unittest tests/test_baseline_audit.py -v
```

Nenhuma dependência externa — apenas Python 3 stdlib nesta fase.

## Números confirmados (Fase 0, corpus RM+TC+RX, sem US)

- 8.402 exames, 5.701 pacientes únicos
- RM: 5.350 · TC: 1.712 · RX: 1.340
- 210 `exam_type` distintos, 7 médicos
- `laterality` nula em 66,2% dos registros (esperado — muitos exam_type não têm lado)
- 0 registros inválidos, 0 duplicatas de `record_id`, 0 anomalias de encoding

Detalhes completos e limitações identificadas em `docs/BASELINE_REPORT.md`.

## Próximo passo proposto (Fase 1)

Restringir a um vertical único de alto volume (candidato: RM de joelho,
911 exames, MSK) o pipeline completo de ingestão → normalização →
section/sentence parser, antes de generalizar para os demais domínios.
Ver justificativa em `docs/architecture.md`.
