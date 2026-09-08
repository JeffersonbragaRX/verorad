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

## Estado atual: mini-eval de fidelidade textual concluída (Fase 4 + Fase 6)

Amostra estratificada de 86 sentenças reais (2 por regra de extração,
cobrindo as 43 regras distintas), lida item a item — **por mim
(Claude), não por um radiologista**: o que foi verificado é fidelidade
textual (o conceito extraído representa exatamente o que a frase diz),
não correção clínica plena. Ver `docs/decisions/0007` para a
metodologia completa e essa distinção.

**4 bugs de precisão real encontrados e corrigidos**, cada um com
evidência do texto real que os expôs:

1. "Verticalizado" sozinho estava sendo tratado como sinônimo de
   degeneração (25 ocorrências afetadas no corpus).
2. "Rotura praticamente completa" era relatada com gravidade "completa"
   pura, superestimando o achado (17 ocorrências).
3. Compartimento específico ("femorotibial medial") gerava um segundo
   conceito redundante e genérico ("femorotibial não especificado")
   pela mesma menção (12 ocorrências).
4. Ligamentos colaterais: espessamento/degeneração intersticial real
   era suprimido sempre que a rotura aguda era negada na mesma frase
   (mesma classe de bug já corrigida em menisco e cruzados na Fase 6).

Todos com teste de regressão, confirmados corrigidos contra o corpus
real (74 testes passando, 11 novos). Limitações remanescentes
(variantes de acentuação/hífen não reconhecidas, faixas de grau
truncadas, construções coordenadas com elisão) documentadas, não
corrigidas — são lacunas de recall, informação omitida, não
informação errada.

```bash
python3 scripts/extract_concepts.py && python3 scripts/compile_report_demo.py
```

## Estado anterior: Fase 6 concluída (Report Compiler, vertical piloto)

Compila um laudo a partir de achados que o médico já decidiu
(`FindingRequest`: estrutura, achado, status, gravidade, localização)
— o compilador **escolhe a frase real do corpus**, nunca gera prosa
livre (sem LLM ainda nesta fase). Se não houver frase real para a
combinação pedida, o achado fica sinalizado como `unresolved`, nunca é
preenchido com texto genérico.

- técnica, achados e impressão montados a partir de frases reais,
  rastreáveis até o médico de origem
- auditor leve embutido: sinaliza contradições no pedido (mesma
  estrutura pedida como presente e ausente) e qualquer estrutura que
  apareça na impressão sem estar nos achados
- **bug de precisão real encontrado e corrigido durante o
  desenvolvimento**: um achado "menisco lateral sem rotura" estava
  sendo resolvido com uma frase real que também afirmava degeneração
  (informação não pedida) — causa raiz era um extrator da Fase 4 que
  tratava rotura e degeneração como mutuamente exclusivas quando são
  eixos clínicos independentes. Corrigido, com teste de regressão. Ver
  `docs/decisions/0006-report-compiler-reuso-de-frase-real.md`
- **limitação estrutural reconhecida, não eliminada**: reuso de frase
  real não garante que a frase contém *apenas* o que foi pedido —
  todo laudo compilado por esta camada é um rascunho e exige revisão
  integral do médico antes do uso

```bash
python3 scripts/compile_report_demo.py   # requer ingest_vertical.py e extract_concepts.py já rodados
```

## Estado anterior: Fase 4 concluída (Clinical Concept Layer, vertical piloto)

Extração de conceitos clínicos estruturados (estrutura, achado, status,
gravidade, localização, medida) a partir das sentenças de
achados/impressão do vertical — **100% por regras/regex, sem LLM**
(`backend/clinical/knee_concepts.py`), com `rule_id` rastreável em
cada conceito.

- 14.675 conceitos extraídos de 18.597 sentenças
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

A avaliação feita até aqui (Claude lendo sentença por sentença) mede
fidelidade textual, não correção clínica — esse teto só é superado com
revisão de um radiologista. Duas opções, não mutuamente exclusivas:

1. **Validação clínica real pelo usuário**: revisar uma amostra dos
   14.675 conceitos extraídos (ou dos laudos compilados) e apontar
   onde a estrutura/rótulo não corresponde ao que ele diria como
   médico — não apenas se bate com o texto, mas se é a forma
   clinicamente correta de descrever o achado.
2. **Fase 8 (UI mínima)**: uma tela simples para inserir achados
   (dropdown de estrutura/achado/gravidade) e ver o laudo compilado em
   tempo real — torna a validação do item 1 prática de fazer, em vez
   de exigir ler JSON.
