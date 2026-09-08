# ARCHITECTURE — LaudoCore (estado no fim da Fase 0)

## O que existe hoje

Apenas a camada de auditoria de dados. Nenhum banco, API, frontend ou
LLM foi implementado ainda — deliberadamente. Ver
`docs/decisions/0001-fase0-antes-de-infra.md`.

```text
laudocore/
├── docs/
│   ├── architecture.md          (este arquivo)
│   ├── data_dictionary.md       (schema real do export RAW)
│   ├── BASELINE_REPORT.md       (saida do baseline, gerada por script)
│   └── decisions/                (ADRs)
├── data/
│   ├── raw/                      (corpus original — FORA do git, ver ADR 0002)
│   ├── staging/                  (vazio — Fase 1)
│   ├── processed/                (vazio — Fase 1)
│   └── derived/qa/                (saidas do baseline: QA_REPORT.json, exam_types.csv, physicians.csv)
├── scripts/
│   └── baseline_audit.py         (Fase 0: le RAW, recalcula, valida, gera relatorios)
└── tests/
    └── test_baseline_audit.py    (criterio de aceite da Fase 0)
```

## Decisão de escopo em relação à ESPECIFICACAO_MESTRA original

A especificação mestra original define uma V1 que já inclui ingestão
completa, parsers de seção/sentença, embeddings, retrieval híbrido,
Clinical Concept Layer genérica para todos os domínios, Report Compiler
e auditor determinístico — construídos em paralelo para RM/TC/RX em
todos os domínios simultaneamente.

Essa ordem foi revisada em conversa com o usuário: o risco concreto de
construir schema genérico para 210 `exam_type` e ~10 domínios antes de
validar qualquer um deles contra uso real é gerar meses de andaime sem
nunca produzir um laudo utilizável. A partir da Fase 1, a recomendação
registrada é: **um vertical único de alto volume primeiro** (candidato
natural: RM de joelho, MSK — 911 exames, é a subespecialidade do
usuário), com o pipeline completo (ingestão → retrieval → compiler →
auditor) rodando de ponta a ponta nesse vertical antes de generalizar
para os demais `exam_type`/domínios. A Fase 0 aqui entregue é neutra em
relação a essa escolha (audita o corpus inteiro), mas a Fase 1 deve
restringir o processamento pesado ao vertical escolhido.

## Onde este código vive

Este projeto foi colocado em `laudocore/` dentro do repositório
`verorad`, que já contém um produto não relacionado (estimativa de idade
óssea via ConvNeXtV2/ONNX, app Streamlit em `app.py`/`atlas.py`/`train.py`
na raiz do repo). Essa decisão de colocação está documentada e justificada
em `docs/decisions/0003-local-do-repositorio.md` — inclui o trade-off
considerado e como desfazer se o usuário preferir um repositório dedicado.
