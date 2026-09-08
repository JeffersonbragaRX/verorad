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

## Cabeçalhos observados por médico (vertical RM_JOELHO_D/RM_JOELHO_E)

Levantamento empírico sobre os 911 laudos do vertical piloto (Fase 1),
usado para construir `backend/parsers/section_parser.py`. Nenhuma
estrutura foi assumida — cada padrão abaixo foi contado no corpus real
antes de virar regra de parsing.

| Médico | Indicação | Técnica | Achados | Impressão | Comparação | Observação estrutural |
|---|---|---|---|---|---|---|
| CAIO (177) | 99,4% | 100% | 100% | 100% | 0,6% | `CABEÇALHO: conteúdo` na mesma linha (`INFORMAÇÕES CLÍNICAS: dor.`) |
| RAFAEL (295) | 100% | 100% | 100% | 100% | 4,7% | Mesmo estilo inline de CAIO |
| NEY (368) | 92,1% | 100% | 100% | 100% | 11,4% | Cabeçalho isolado em linha própria (`INDICAÇÃO CLÍNICA:` seguido de conteúdo na(s) linha(s) seguinte(s)); único a usar `ANÁLISE COMPARATIVA:` com regularidade |
| SAMIR (71) | 4,2% | 100% | 100% | **4,2%** | 0% | Estrutura distinta: `TÉCNICA DE EXAME:` / `OS SEGUINTES ASPECTOS FORAM OBSERVADOS:`; **não separa impressão do corpo do laudo na maioria dos casos** — isso é um traço real do estilo de ditado dele, não uma falha do parser |

Descoberta relevante: um mesmo rótulo textual (`INFORMAÇÕES CLÍNICAS`,
`TÉCNICA`) pode aparecer **isolado em sua própria linha** (NEY, SAMIR)
ou **combinado com o conteúdo na mesma linha** (CAIO, RAFAEL). O parser
trata os dois formatos; um parser ingênuo que só reconhece cabeçalho
isolado subestimaria drasticamente a cobertura de CAIO/RAFAEL (medido:
0% de "técnica" antes da correção, 100% depois).

Também aparece, em ~9% dos laudos de NEY, uma linha solta de código
CID/ICD-10 (`CID M25.5`, e variantes de digitação `CDI`/`CIS`) logo
após o cabeçalho de indicação — tratada como conteúdo da própria seção
de indicação, não como um cabeçalho novo.

Cabeçalhos residuais não mapeados (3 ocorrências em 911 laudos,
mantidos como seção `other` para revisão manual, não classificados por
adivinhação): `ACHADO ADICIONAL:`, `ACHADOS ADICIONAIS:`,
`REFERÊNCIA BIBLIOGRÁFICA:`.

## Vocabulário clínico do joelho (Fase 4 — Clinical Concept Layer)

Estruturas com frequência real nas 18.597 sentenças de achados/impressão
do vertical (contagem de sentenças que mencionam o termo, não de
ocorrências — ver `backend/clinical/knee_concepts.py`):

| Termo/estrutura | Sentenças | Termo/estrutura | Sentenças |
|---|---|---|---|
| patela | 5.088 | corpo do menisco | 329 |
| derrame articular | 1.276 | platô tibial | 301 |
| condropatia | 1.198 | tendão quadríceps | 283 |
| menisco medial | 1.117 | corno anterior | 273 |
| corno posterior | 1.085 | edema ósseo | 224 |
| tendinopatia | 921 | ligamento cruzado posterior | 201 |
| menisco lateral | 851 | plica | 156 |
| côndilo femoral | 474 | tendão patelar | 108 |
| ligamento cruzado anterior | 467 | ligamento colateral lateral | 70 |
| complexo retinacular | 463 | cisto parameniscal | 63 |
| cisto poplíteo | 461 | pata de ganso | 31 |
| ligamento colateral medial | 459 | cisto gangliônico | 21 |
| artropatia degenerativa | 453 | | |

Este vocabulário orientou o schema de extração de conceitos clínicos
(estrutura, achado, status, gravidade, localização). Cobertura obtida
com regras (sem LLM): 58,0% das sentenças produzem pelo menos um
conceito — ver `docs/decisions/0005-clinical-concept-layer-por-regras.md`,
`0007-mini-eval-textual-fase4-fase6.md` e `0008-fila-de-revisao-clinica.md`
para o método, as correções aplicadas e as limitações reconhecidas.

## Pendência conhecida

`US` (ultrassonografia) está no escopo do manifest mas sem registros neste
lote — o próprio usuário confirmou que a exportação de US ainda está em
andamento. Qualquer reprocessamento futuro do baseline precisa tratar isso
como um **novo lote a integrar**, não como correção do lote atual.
