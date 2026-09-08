# DATA_DICTIONARY — corpus RAW (export CMS)

Este documento descreve o schema **real observado** no export recebido
(`CMS_RADIOLOGY_CORPUS_PRODUCTION_V2_1_1_3MONTHS_FAST_AUDITED`), validado
programaticamente por `scripts/baseline_audit.py` sobre os 8.402 registros
do snapshot `2026-09-07T18-47-50-654Z`. Nenhum campo abaixo foi assumido —
todos foram checados linha a linha.

## Formato do arquivo

- `manifest.json`: metadados do lote (janela de datas, modalidades no
  escopo, lista de médicos permitidos, schema declarado, contagem total).
- `stats.json`: estatísticas agregadas calculadas pelo CMS de origem
  (usadas aqui apenas como **conferência cruzada**, nunca como fonte
  primária de verdade — ver seção "Cruzamento" do `BASELINE_REPORT.md`).
- `reports_NNNNN.jsonl`: um registro JSON por linha, UTF-8, sem BOM.

## Campos de `reports_*.jsonl`

| Campo | Tipo observado | Nulo? | Observações |
|---|---|---|---|
| `record_id` | int | não | Único dentro do snapshot (0 duplicatas no lote atual). Não é estável entre snapshots diferentes do mesmo export — não usar como chave permanente sem reconfirmar. |
| `patient_id` | string numérica | não | Identificador pseudonimizado pelo CMS de origem. Não é nome nem CPF. `manifest.json` declara explicitamente que nomes e data de nascimento **não** fazem parte do export. |
| `age_at_exam` | int | não | Idade em anos na data do exame. |
| `sex` | string (`M`/`F`) | não | Sem valores fora desse domínio no lote atual. |
| `exam_datetime` | string `DD/MM/YYYY HH:MM` | não | Validado contra a janela declarada (2026-06-06 a 2026-09-06); 0 registros fora da janela. |
| `domain` | string | não | Domínio clínico (`MSK`, `NEURO`, `ABDOME`, `TORAX`, `PELVE_GU`, `CABECA_PESCOCO`, `CARDIO`, `MAMA`, `VASCULAR`, `INDEFINIDO`). Atribuído pelo CMS de origem, não pelo nosso pipeline. |
| `modality` | string | não | `RM`, `TC` ou `RX` neste lote. `US` está no escopo declarado do manifest mas **ainda não tem registros** neste export. |
| `anatomy` | string | não | Região anatômica, granularidade inconsistente entre exam_type (ver `exam_types.csv`). |
| `laterality` | string ou `null` | **sim, 66,2% dos registros** | `null` predomina porque muitos exam_type não têm lado (coluna, tórax, encéfalo). Antes da Fase 4, será preciso distinguir "não aplicável" de "lado não informado" por domínio — hoje o dado não permite essa distinção sozinho. |
| `exam_type` | string | não | Código composto pelo CMS (ex.: `RM_JOELHO_D`). 210 valores distintos no lote. Tratar como **insumo bruto a normalizar na Fase 2**, não como taxonomia final — há variantes de granularidade (`RM_QUADRIL_D` vs `RM_QUADRIL_BILATERAL` vs `RM_QUADRIL`). |
| `study_description_raw` | string | não | Descrição original do procedimento (ex.: `"Coluna^Lombar"`), formato de RIS/PACS. |
| `doctor` | string | não | 7 médicos no lote atual: NEY, SERGIO, RAFAEL, JULIANA, CAIO, SAMIR, SAMIRA — todos presentes em `manifest.json.allowed_doctors`. |
| `report_text` | string | não (vazio não ocorre) | Texto integral do laudo, incluindo cabeçalho de técnica. Nenhuma anomalia de encoding detectada (mojibake, replacement char, caractere de controle) no lote atual. |

## O que este export explicitamente NÃO contém

Conforme `manifest.json.note`: SUID, Accession, Ticket, MPIDTicket, URLs
autenticadas, nomes de pacientes e datas de nascimento. Isso não elimina
o risco de reidentificação por combinação de `patient_id` + `exam_datetime`
+ `doctor` com outras bases (ex.: agenda do serviço) — ver
`docs/decisions/0002-dados-fora-do-git.md`.

## Snapshots recebidos

O ZIP `TCRMRX.zip` contém três diretórios sob
`CMS_CORPUS_2026-06-06_A_2026-09-06/`, todos com a mesma janela de datas,
gerados no mesmo dia (2026-09-07) em horários diferentes (03:02, 13:27,
18:47 UTC) e com contagens crescentes (5.350 → 7.062 → 8.402 registros).
São **snapshots cumulativos do mesmo export em andamento**, não corpora
distintos — o mais recente (18:47) contém os anteriores. O baseline usa
apenas o mais recente; os demais ficam em `data/raw/` como histórico, sem
uso analítico.

## Pendência conhecida

`US` (ultrassonografia) está no escopo do manifest mas sem registros neste
lote — o próprio usuário confirmou que a exportação de US ainda está em
andamento. Qualquer reprocessamento futuro do baseline precisa tratar isso
como um **novo lote a integrar**, não como correção do lote atual.
