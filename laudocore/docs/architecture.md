# ARCHITECTURE — LaudoCore (estado no fim da Fase 1)

## O que existe hoje

Auditoria de dados (Fase 0) + Data Engine restrito a um vertical único
(Fase 1: RM_JOELHO_D + RM_JOELHO_E, 911 laudos). Nenhuma API, frontend,
retrieval ou LLM foi implementado ainda — deliberadamente. Ver
`docs/decisions/0001-fase0-antes-de-infra.md`.

```text
laudocore/
├── docs/
│   ├── architecture.md          (este arquivo)
│   ├── data_dictionary.md       (schema RAW + cabecalhos por medico)
│   ├── BASELINE_REPORT.md       (saida da Fase 0)
│   └── decisions/                (ADRs)
├── data/
│   ├── raw/                      (corpus original — FORA do git, ver ADR 0002)
│   ├── staging/                  (vazio — reservado)
│   ├── processed/                (laudocore.db, SQLite — FORA do git, ver ADR 0002/0004)
│   └── derived/qa/                (QA_REPORT.json, QA_REPORT_FASE1.json, exam_types.csv, physicians.csv)
├── backend/
│   ├── normalization/text_normalization.py   (RAW -> clean -> normalized, hashes A/B)
│   ├── parsers/section_parser.py             (secoes, orientado a dados por medico)
│   ├── parsers/sentence_parser.py            (sentencas por secao)
│   └── db/schema.py                          (schema SQLite — reports/report_sections/sentences)
├── scripts/
│   ├── baseline_audit.py         (Fase 0)
│   └── ingest_vertical.py        (Fase 1: ingestao do vertical piloto, comando unico, idempotente)
└── tests/
    ├── test_baseline_audit.py
    ├── test_normalization.py
    ├── test_section_parser.py
    ├── test_sentence_parser.py
    └── test_ingest_vertical.py   (integracao — requer corpus local, ver skip condicional)
```

## Fase 1 — o que o parser aprendeu com os dados reais

O parser de seções não usa um único conjunto de cabeçalhos: cada
médico do vertical piloto escreve de forma diferente (ver
`docs/data_dictionary.md`, "Cabeçalhos observados por médico"). Dois
achados mudaram o design em relação à primeira versão do parser:

1. Cabeçalho e conteúdo podem estar na mesma linha (`TÉCNICA: texto…`)
   ou em linhas separadas — dependendo do médico. Um parser que só
   reconhece uma das formas subestima silenciosamente a cobertura de
   metade dos médicos (medido: 0% → 100% de cobertura de "técnica"
   para CAIO antes/depois da correção).
2. Ausência de seção pode ser um traço real de estilo (SAMIR não separa
   "impressão" do corpo do laudo em 95,8% dos casos) — o parser não
   fabrica uma seção que não existe no texto; isso fica registrado como
   dado, não como falha de parsing.

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
