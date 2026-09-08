# BASELINE_REPORT — LaudoCore Fase 0

Gerado em: 2026-09-08T02:18:24.823620Z

Snapshot usado: `CMS_CORPUS_2026-06-06_A_2026-09-06_2026-09-07T18-47-50-654Z`

Motivo: o ZIP recebido contem tres exports cumulativos do mesmo lote, gerados no mesmo dia (03:02, 13:27 e 18:47 UTC de 2026-09-07). Nao sao corpora distintos — sao snapshots sucessivos do mesmo processo de export em andamento. Foi usado o snapshot com maior contagem de registros declarada em `manifest.json` (18:47, 8.402 registros); os demais foram preservados em `data/raw/` como historico, mas nao entram nas estatisticas abaixo.

## Escopo declarado pelo export

- Janela: 2026-06-06 a 2026-09-06
- Modalidades no escopo do lote: RM, TC, RX, US
- Status do export: `approved`, `complete: False`
- **US ainda nao esta presente neste export** (confirmado pelo usuario e por `ScopedCompletion.US: false` / ausencia de registros US no lote atual). Nao tratar a ausencia de US como corpus completo — sera um lote de ingestao futuro.

## Criterio de Fase 0: 100% das linhas lidas ou justificadas

- Linhas lidas: 8402
- Registros validos: 8402
- Registros invalidos (com motivo registrado em QA_REPORT.json): 0
- **Verificacao: 8402 == 8402 + 0 → OK**
- record_id duplicados detectados: 0
- Pacientes unicos (patient_id distintos): 5701

## Contagens reprodutiveis (recalculadas a partir do JSONL bruto, nao do export)

### Por modalidade
- RM: 5350
- TC: 1712
- RX: 1340

### Por dominio
- MSK: 5379
- NEURO: 835
- ABDOME: 600
- TORAX: 478
- PELVE_GU: 464
- CABECA_PESCOCO: 327
- CARDIO: 219
- MAMA: 47
- VASCULAR: 36
- INDEFINIDO: 17

### Por medico
- NEY: 2245
- SERGIO: 1748
- RAFAEL: 1528
- JULIANA: 1335
- CAIO: 977
- SAMIR: 522
- SAMIRA: 47

- exam_type distintos: 210
- Top 10 exam_type por volume:
  - RM_COLUNA_LOMBAR: 770
  - RM_JOELHO_D: 463
  - RM_JOELHO_E: 448
  - RM_ENCEFALO: 394
  - TC_TORAX: 356
  - RM_COLUNA_CERVICAL: 333
  - RX_COLUNA_LOMBAR: 305
  - RM_PELVIS: 296
  - RM_OMBRO_D: 271
  - RM_OMBRO_E: 224

## Qualidade e anomalias

- Campos ausentes por tipo: nenhum
- Erros de tipo por campo: nenhum
- laterality nula: 5560 de 8402 (66.2%)
- Datas fora da janela declarada (2026-06-06 a 2026-09-06): 0
- modality fora de ['RM', 'RX', 'TC']: 0
- Possiveis anomalias de encoding (mojibake / caractere de controle / replacement char): 0
- Duplicatas de TEXTO exato (hash sha256 do report_text): 512 grupos, 1274 registros — **nao removidos**: podem ser exames reais distintos com laudo identico.
- Duplicatas de texto normalizado (casefold + espacos): 514 grupos, 1278 registros — mesma ressalva.
- Tamanho de report_text (caracteres): min=127, mediana=1504, media=1559.4, max=6337

## Cruzamento contra os numeros do proprio export (nao aceitos sem verificacao)

- records declarado no manifest: 8402 vs recalculado: 8402 → CONFERE
- unique_patients declarado: 5701 vs recalculado: 5701 → CONFERE
- ByModality do export vs recalculado → CONFERE
- LateralityNull do export (5560) vs recalculado (5560) → CONFERE

## Riscos e limitacoes identificados nesta fase

- O export ja chega filtrado/'auditado' pelo sistema de origem (CMS) — este baseline valida consistencia interna do JSONL recebido, mas nao audita o pipeline de extracao do CMS em si (fonte fora do nosso controle direto).
- `laterality` nula em maioria dos registros (ver percentual acima) — esperado para exam_type sem lado (ex.: coluna, torax), mas precisa ser confirmado por dominio antes da Fase 4 (Clinical Concept Layer), para nao confundir 'nao aplicavel' com 'lado nao informado'.
- `study_description_raw` e `exam_type` sao derivados pelo CMS de origem, nao pelo nosso pipeline — a taxonomia (Fase 2) precisa tratar `exam_type` como *insumo a normalizar*, nao como taxonomia final (ja existem variantes como `RM_QUADRIL_D` vs `RM_QUADRIL_BILATERAL`).
- US ainda ausente: qualquer estatistica futura de 'corpus completo' deve reprocessar este baseline quando o lote US chegar, em vez de apenas somar.
- Corpus bruto (JSONL com report_text e patient_id) foi mantido apenas em disco local (`data/raw/`, fora do controle de versao) e NAO foi commitado no repositorio Git — contém texto clinico real e patient_id; ver `docs/decisions/0002-dados-fora-do-git.md`.

## Proximo passo proposto

Fase 1 (Data Engine) restrita a um unico vertical de alto volume (candidato: RM_JOELHO_D + RM_JOELHO_E, 911 exames, MSK) — ingestao no schema `reports`, normalizacao RAW/clean/normalized, section parser e sentence parser, antes de generalizar para os demais exam_type.
