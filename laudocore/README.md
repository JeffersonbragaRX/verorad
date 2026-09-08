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

## Estado atual: Fase 4 concluída (Clinical Concept Layer, vertical piloto)

Extração de conceitos clínicos estruturados (estrutura, achado, status,
gravidade, localização, medida) a partir das sentenças de
achados/impressão do vertical — **100% por regras/regex, sem LLM**
(`backend/clinical/knee_concepts.py`), com `rule_id` rastreável em
cada conceito.

- 13.665 conceitos extraídos de 18.597 sentenças
- 56,7% das sentenças produzem pelo menos um conceito (cobertura
  aproximada de recall — **não é medida de precisão**, ver ressalva
  abaixo)
- 1 bug real de precisão encontrado e corrigido durante o
  desenvolvimento (via revisão manual de amostra): confusão entre o
  osso "patela" e o tendão "patelar" por match de substring
- **sem gold standard ainda**: não há conjunto de avaliação anotado
  manualmente para medir precisão real — ver
  `docs/decisions/0005-clinical-concept-layer-por-regras.md`

```bash
python3 scripts/extract_concepts.py   # requer ingest_vertical.py já rodado
```

## Estado anterior: Fase 1 concluída (vertical piloto)

Vertical piloto: **RM de joelho** (`RM_JOELHO_D` + `RM_JOELHO_E`, 911
laudos, MSK — subespecialidade do usuário). Pipeline completo de
ponta a ponta: normalização (RAW/clean/normalized) → hashes A/B →
section parser (orientado pelos cabeçalhos reais de cada um dos 4
médicos do vertical) → sentence parser → persistência em SQLite.

- 911 laudos ingeridos, 20.498 sentenças extraídas
- `technique` e `findings` presentes em 100% dos laudos dos 4 médicos
- `indication`/`impression` variam por médico — inclusive um médico
  (SAMIR) que genuinamente não separa impressão do corpo do laudo em
  95,8% dos casos; o parser não inventa uma seção que não existe
- apenas 3 cabeçalhos em 911 laudos não reconhecidos automaticamente
  (deixados para revisão manual, não classificados por adivinhação)
- pipeline idempotente (mesmo resultado em execuções repetidas) e
  testado (23 testes novos, além dos 6 da Fase 0)

Detalhes: `docs/data_dictionary.md` (seção "Cabeçalhos observados por
médico") e `data/derived/qa/QA_REPORT_FASE1.json`.

```bash
python3 scripts/ingest_vertical.py
python3 -m unittest discover -s tests -v
```

## Estado anterior: Fase 0 concluída

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

## Próximo passo proposto

Duas opções, não mutuamente exclusivas:

1. **Mini-eval do Clinical Concept Layer**: anotar manualmente 50-100
   sentenças (idealmente pelo próprio usuário) com o conceito
   "correto" esperado, medir precisão/recall reais contra esse gold
   standard antes de confiar na camada de conceitos em qualquer uso
   downstream — recomendado em `docs/decisions/0005`.
2. **Fase 6 (Report Compiler), restrita ao vertical**: usar os
   conceitos já extraídos para montar um laudo de RM de joelho a
   partir de achados fornecidos pelo médico, sem geração livre por
   LLM ainda — o próximo ponto onde "fidelidade clínica > velocidade"
   (seção 36 da especificação) passa a ser testável na prática.
