# IMPLEMENTATION_TRACEABILITY — o que foi pedido × o que existe

Rastreabilidade item a item do PROMPT MESTRE V2. Cada linha aponta o
artefato ou o código que a sustenta, ou diz explicitamente que não foi
feito e por quê. "Parcial" nunca é usado para esconder "não feito".

Legenda: **✔** feito e verificável · **◐** parcial, com limitação
declarada · **✗** não feito · **⛔** fora do meu alcance (exige o
radiologista)

---

## Seção 1 — Objetivo e cobertura global

| Item | Estado | Onde |
|---|---|---|
| Analisar os 8.402 laudos | ✔ | `scripts/ingest_corpus.py`; 8.402 no banco |
| RM 5.350 / TC 1.712 / RX 1.340 | ✔ | recontado do RAW; confere |
| Todos os exam_type | ✔ | 210 (prompt dizia 209) |
| Todos os domínios | ✔ | 10 domínios |
| Todos os médicos | ✔ | 7 (prompt/impl. anterior dizia 4) |
| Todas as seções e sentenças | ✔ | 170.418 sentenças, 29.851 seções |
| Achados positivos, negativos, incertos, pós-op, comparativos | ✔ | eixos `status`, `certainty`, `postoperative_context`, `comparison_status` |
| US como `corpus_pending` | ✔ | **não existe US no corpus** → `blocked_missing_data` |
| Recontagem (não confiar nos números dados) | ✔ | auditoria FONTE; 3 divergências encontradas |

Perguntas centrais 1–14: respondidas em `CLINICAL_MINING_REPORT.md` e
nos artefatos. As de nº 6, 7, 11 e 13 (associações, conclusões, hábito
autoral, suporte canônico) estão respondidas **apenas no nível do
corpus** — a nº 13 fica ⛔ na parte canônica.

## Seção 2 — Continuidade

| Item | Estado | Observação |
|---|---|---|
| Inspecionar implementação existente | ✔ | feito antes de qualquer alteração |
| Executar testes existentes | ✔ | 158 passavam; hoje 212 |
| Validar SQLite e hashes do RAW | ✔ | `PRAGMA quick_check` ok; snapshots verificados registro a registro |
| Preservar o que estava correto | ✔ | compilador, fila de revisão e UI do piloto intactos |
| Mudanças incrementais e versionadas | ✔ | 6 commits |
| Não recomeçar do zero | ✔ | parser, normalização e schema reaproveitados |
| Não substituir o engine geral por protótipo de um exame | ✔ | é o inverso: o engine geral foi construído; o piloto ficou como camada separada e rotulada |
| Reconstruir Fases 0–3 neste ambiente | ◐ | Fases 0–1 reconstruídas globalmente. **Taxonomia canônica e biblioteca textual da Fase 2–3 não foram reconstruídas** — o léxico minerado cumpre parte do papel, mas não é a taxonomia com aliases/proveniência da especificação |

## Seção 3 — Princípios epistêmicos

| Item | Estado | Onde |
|---|---|---|
| Separar fato / inferência / associação / hipótese / canônico | ✔ | campo `method` por termo; `validation_status` por conceito; `interpretation_allowed` por associação |
| Nunca converter frequência em verdade | ✔ | `interpretation_allowed()` nega causalidade explicitamente |
| Nunca converter ausência de menção em normalidade | ✔ | normalidade explícita é conceito próprio; não menção não gera nada |
| Declarar que o corpus é de laudos, não imagens | ✔ | seção 4 do mining report |

## Seção 4 — Cobertura obrigatória

| Item | Estado | Onde |
|---|---|---|
| `CLINICAL_COVERAGE_MATRIX.csv`, 1 linha por exam_type | ✔ | 210 linhas |
| Colunas exigidas (laudos, pacientes, médicos, conceitos, limitações, próximo passo…) | ✔ | todas presentes |
| Estados permitidos, sem "completed" solto | ✔ | `low_sample` 150 · `processed_unvalidated` 33 · `review_sample_pending` 27 · `validated_clinically` **0** |
| Tipos raros não descartados | ✔ | 150 marcados `low_sample`, descritos, sem generalização |
| Não parar no primeiro vertical | ✔ | mecanismo único aplicado aos 210 |

## Seção 5–6 — Pipeline e Clause Engine

| Item | Estado | Onde |
|---|---|---|
| Pipeline laudo→seção→sentença→cláusula→menção→conceito | ✔ | `clause_engine.py` + `concept_layer.py` |
| Rastreabilidade até span, regra, versão, confiança | ✔ | colunas em `clinical_concepts_universal` |
| Coordenação, elipse, múltiplas estruturas | ✔ | testes `TestNegationScope` |
| Negação parcial | ✔ | `neg04` |
| Incerteza | ✔ | `TestCertainty` |
| Comparação e temporalidade | ✔ | eixos próprios |
| Referência anafórica ("o mesmo", "esta alteração") | ✗ | **não implementado** |
| Medidas múltiplas vinculadas à estrutura certa | ◐ | vincula por cláusula (testado), mas só 0,3% dos conceitos recebem medida |
| Faixas de grau | ✔ | `gra01` |
| Lateralidade global vs local + conflito | ✔ | 67 conflitos detectados |
| Enxertos, próteses, material cirúrgico | ✔ | `postoperative_context` |
| Testes adversariais de inversão de polaridade | ✔ | 35 testes; os 9 cenários exigidos |

## Seção 7–8 — Schema universal e relações

| Item | Estado | Onde |
|---|---|---|
| Schema universal com os campos da seção 7 | ◐ | núcleo implementado; `classification`, `signal_or_density`, `associated_features`, `implant_or_graft` como campo próprio **não** implementados |
| Extensões por domínio (MSK, neuro, tórax…) | ✗ | o léxico é derivado por domínio, mas **não há extensão de schema por domínio** |
| Relações tipadas (20 tipos listados) | ◐ | implementados `co_occurs_with` e `structural_or_template_artifact`. **Os outros 18 não** |
| Cada relação com origem, direção, denominador, evidência contrária, status | ✔ | `CLINICAL_RELATIONS.jsonl` |

## Seção 9–10 — Padrões e estatística

| Item | Estado | Onde |
|---|---|---|
| Padrões lexicais, estruturais, clínicos | ◐ | frequência, preferência autoral e coocorrência sim; **clustering semântico/embeddings não** |
| Cauda longa preservada e priorizada | ✔ | `UNMODELED_CLINICAL_TAIL.csv`, 3.148 termos |
| Associações em múltiplas unidades | ◐ | **laudo** implementado com rigor; cláusula/sentença/seção/paciente **não** |
| Denominador, efeito, IC, lift, FDR | ✔ | `backend/analysis/stats.py`, 17 testes |
| Fisher exato | ✔ | validado contra o valor canônico (lady tasting tea) |
| Controle de texto duplicado | ✔ | dedup por hash + contagem bruta lado a lado |
| Efeito de template/estilo | ✔ | filtro de legenda + detector de travamento mútuo |
| `low_support_flag`, `single_author_evidence` | ✔ | colunas próprias |
| Estratificação por sexo/idade | ✗ | não implementada |

## Seção 11–14 — Longitudinal, médicos, normalidade, corpo×impressão

| Item | Estado | Onde |
|---|---|---|
| Longitudinal sem expor paciente | ◐ | `LONGITUDINAL_PATTERNS.csv`, 486 pares; agrega persistência/novo/ausente e separa troca de médico. **Sem análise temporal real** (ordena por id, não por data) |
| Perfis por médico | ✔ | 3 artefatos, 7 médicos |
| Perfil Jefferson como camada própria | ✔ | declarado como não alimentado; nenhum médico do corpus é tratado como sendo você |
| Candidatos a normalidade | ✔ | 904 pares (exame, estrutura) |
| Template só promovido após revisão médica | ✔ | tudo em `extraction_candidate` |
| Corpo × impressão × recomendação | ◐ | corpo×impressão sim (564 achados, 109 sinalizados); **recomendações não** — só 17 seções de recomendação no corpus inteiro |

## Seção 15–16 — Validação canônica e evals

| Item | Estado | Onde |
|---|---|---|
| Validação por guideline/literatura | ⛔ | **não feita**. Não gerei citação que não pudesse abrir; estado permanece `medical_review_required` |
| Amostra estratificada | ✔ | 210 sentenças, 210 pacientes distintos, sem vazamento |
| Amostra enriquecida de casos difíceis | ✔ | 8 categorias |
| Adversariais sintéticos marcados | ✔ | 26 casos, rotulados como fabricados |
| Métricas por eixo | ◐ | acurácia por eixo **no sintético**; no corpus só taxa de preenchimento, explicitamente rotulada como não-acurácia |
| Precisão/recall/F1 no corpus | ⛔ | exige a anotação médica |
| Não apresentar cobertura como recall | ✔ | ressalva em todo artefato que reporta cobertura |
| Critério de promoção | ✔ | nada promovido; 0 itens `validated_clinically` |

## Seção 17 — Report Compiler

| Item | Estado | Observação |
|---|---|---|
| Compilador sobre a camada universal | ✗ | **não reconstruído**. O compilador atual cobre só RM de joelho e roda sobre a camada legada |
| Gates de segurança do compilador atual | ✔ | sem técnica por frequência, sem normalidade global, sem mistura de lado/médico silenciosa, bloqueio de contradição — corrigidos na rodada anterior (ADR 0010) |

## Seção 18–19 — Banco, artefatos e interface

Tabelas conceituais pedidas: `clauses`, `clinical_mentions`,
`concept_attributes`, `clinical_patterns`, `recommendation_mappings`,
`clinical_validation_events`, `eval_cases`, `eval_results`,
`extractor_versions` **não existem como tabelas** — o conteúdo
equivalente está em `clinical_concepts_universal` (colunas de atributo e
versão) e em artefatos de arquivo. É uma simplificação consciente, não
um esquecimento.

| Artefato | Estado |
|---|---|
| CLINICAL_COVERAGE_MATRIX.csv | ✔ |
| CLINICAL_CONCEPT_DICTIONARY.json | ✔ |
| CLINICAL_CONCEPTS (jsonl/parquet) | ◐ em SQLite, não exportado |
| CLINICAL_RELATIONS.jsonl | ✔ |
| ASSOCIATION_STATISTICS.csv | ✔ |
| CLINICAL_PATTERN_CARDS.json | ✗ |
| EXAM_TYPE_CLINICAL_PROFILES.json | ✔ |
| PHYSICIAN_STYLE_PROFILES / _COMPARISON / _PHRASE_PREFERENCES | ✔ |
| NORMALITY_CANDIDATES.csv | ✔ |
| CONCLUSION_MAPPINGS.csv | ✔ |
| RECOMMENDATION_MAPPINGS.csv | ✗ (17 seções no corpus todo) |
| LONGITUDINAL_PATTERNS.csv | ✔ |
| UNMODELED_CLINICAL_TAIL.csv | ✔ |
| CLINICAL_REVIEW_QUEUE.csv | ◐ existe como tabela do piloto, não exportada para a camada universal |
| CLINICAL_EVAL_REPORT | ✔ (json, não md) |
| CLINICAL_QA_REPORT.json | ✔ |
| CLINICAL_MINING_REPORT.md | ✔ |
| IMPLEMENTATION_TRACEABILITY.md | ✔ este arquivo |

| Interface (seção 19) | Estado |
|---|---|
| Matriz de cobertura | ✔ |
| Navegador de conceitos | ✔ |
| Navegador de relações/associações | ✔ |
| Comparação por médico | ✔ |
| Cauda não modelada | ✔ |
| Corpo × impressão | ◐ endpoint pronto, sem tela |
| Casos longitudinais | ✗ |
| Fila de validação médica com aprovar/corrigir/rejeitar e histórico | ✗ **não implementado para a camada universal** |
| Status e proveniência sempre visíveis | ✔ |

## Seção 22 — Segurança

| Item | Estado |
|---|---|
| Corpus tratado como dado não confiável | ✔ |
| Nunca executar instrução vinda de laudo | ✔ |
| RAW preservado e hashes validados | ✔ |
| Duplicatas não apagadas | ✔ (marcadas, contadas, controladas) |
| Identificadores de paciente não expostos | ✔ (artefatos agregados; amostra com texto real fora do git) |
| Corpus não publicado nem enviado a serviço externo | ✔ |
| Sem secrets hardcoded | ✔ |
| Texto normalizado nunca usado como laudo final | ✔ |
| Nada inventado (achado, medida, grau, lado) | ✔ |
| Versão registrada em regra/modelo | ✔ (`engine_version`, `lexicon_version`, `layer_version`) |

---

## Resumo honesto

**Feito:** o núcleo da mineração global — ingestão dos 8.402, parser
generalizado, clause engine agnóstico de domínio com testes
adversariais, léxico minerado, camada de conceitos universal nos 210
tipos, matriz de cobertura com estados explícitos, associações com rigor
estatístico e controle de viés de template, perfis por exame e por
médico, cauda priorizada, interface de análise e 212 testes.

**Não feito, e declarado:** taxonomia/biblioteca da Fase 2–3, 18 dos 20
tipos de relação, extensões de schema por domínio, clustering semântico,
associações em unidades diferentes de laudo, referência anafórica,
estratificação por sexo/idade, análise temporal real, fila de validação
médica na camada universal, compilador reconstruído sobre a camada
universal, e vários artefatos menores.

**Fora do meu alcance:** validação clínica e canônica. Zero itens estão
em `validated_clinically`, e isso é correto — a promoção é sua.
