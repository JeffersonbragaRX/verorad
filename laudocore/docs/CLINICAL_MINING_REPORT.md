# CLINICAL_MINING_REPORT — mineração clínica do corpus radiológico

Execução do PROMPT MESTRE V2 sobre o corpus inteiro. Este documento
descreve o que foi feito, o que os dados mostram e — com o mesmo peso —
o que **não** foi estabelecido.

Regra que governa cada número aqui: é padrão **documentado neste
corpus**, nunca conhecimento clínico. Nenhum conteúdo produzido nesta
execução está validado clinicamente; tudo está em
`extraction_candidate` ou `corpus_only`.

---

## 1. Escopo processado (recontado do RAW, não herdado)

| | Valor |
|---|---|
| Laudos | **8.402** |
| Pacientes distintos (pseudônimo) | 5.701 |
| Sentenças | 170.418 |
| Sentenças clínicas (achados + impressão) | 150.868 |
| Tipos de exame | **210** |
| Médicos | **7** |
| Domínios | 10 |
| Modalidades | RM 5.350 · TC 1.712 · RX 1.340 |

Divergências em relação aos números de partida do prompt, verificadas
contra o RAW:

- **210 tipos de exame**, não 209.
- **7 médicos**, não 4. A implementação anterior via 4 porque só 4
  laudam RM de joelho — o vertical, não o corpus.
- **Ultrassonografia não existe neste corpus.** Não é pendência de
  modelagem: é `blocked_missing_data`.

Integridade dos snapshots: 5.350 ⊂ 7.062 ⊂ 8.402, verificada registro a
registro, com **zero divergência de texto** nos registros comuns. A
seleção de snapshot agora valida essa propriedade e falha fechada em
caso de conflito, em vez de confiar no maior `manifest.records`.

**1.274 laudos (15%) têm texto exatamente duplicado**, em 512 grupos.
Isso não é erro do corpus — é o mesmo laudo repetido entre exames — mas
contamina qualquer estatística de coocorrência e por isso é controlado
explicitamente na Fase 4D.

---

## 2. O que foi construído

### 2.1 Parser de seções global

O parser anterior foi calibrado nos 911 laudos de RM de joelho. Medido
sobre o corpus inteiro, falhava fora dele:

| Modalidade | Cabeçalho não reconhecido | Sem seção de achados |
|---|---|---|
| RM | 39,2% → **5,0%** | 5,9% → **0,4%** |
| TC | 48,2% → **6,8%** | 6,4% → **0,0%** |
| RX | 95,3% → **0,3%** | **96,2% → 0,6%** |

A causa do colapso em RX não era vocabulário: era arquitetural. Um
cabeçalho desconhecido **reclassificava todo o resto do laudo** como
`other`, e RX não usa `RELATÓRIO:` — abre os achados com uma frase-guia
("As radiografias digitais ... mostram:"). Três mudanças corrigiram:
cabeçalho desconhecido virou subseção rotulada da seção corrente (nunca
troca o tipo); bloco de título reconhecido por posição e forma; achados
implícitos detectados e **marcados como implícitos**, com rastreabilidade
(`implicit_lead_in`, `implicit_no_header`) — nunca apresentados como se
houvesse cabeçalho explícito.

### 2.2 Clause Engine (Fase 4A)

Adaptação ao português do padrão NegEx/ConText: cada cue (negação,
normalidade, incerteza, temporalidade, comparação, pós-operatório,
qualificador etiológico) tem posição, direção e escopo terminado por
marcador de fronteira. Consultas são **por posição da menção**, nunca
por sentença inteira.

35 testes adversariais, incluindo os 9 cenários exigidos e casos fora do
MSK (neuro, tórax, abdome, RX) — o motor é compartilhado por todas as
modalidades e precisa ser testado como tal.

### 2.3 Léxico derivado do corpus (Fase 4B)

Escrever um extrator por tipo de exame significaria 210 extratores. Em
vez disso, o vocabulário é **minerado do próprio corpus**: 6.247 termos,
cada um com a evidência distribucional que sustenta sua classe e o
**método** usado (`corpus_positional`, `morphological`,
`model_knowledge`). Métodos têm força epistêmica diferente e ficam
registrados por termo.

| Classe | Termos |
|---|---|
| anatomy | 1.078 |
| finding | 690 |
| modifier | 705 |
| descriptor | 257 |
| severity / morphology / distribution | 35 / 32 / 41 |
| não classificado (cauda) | 3.148 |

### 2.4 Camada de conceitos universal

Schema universal (seção 7 do prompt) aplicado às 150.868 sentenças
clínicas: **99.921 conceitos**, com proveniência completa
(laudo/seção/sentença/span/regra/versão/confiança).

- Cobertura **superficial**: 53,2% das sentenças geraram ≥1 conceito.
- Estrutura anatômica ligada: 53,5% dos conceitos.
- Status: 69.431 presentes · 18.838 normalidade explícita · 11.652 negados.
- **67 conflitos de lateralidade** detectados (lado do metadado ≠ lado
  citado no corpo) — o caso adversarial que o prompt exige, capturado e
  sinalizado em vez de resolvido em silêncio.

---

## 3. O que os dados mostram

### 3.1 Matriz de cobertura (210 linhas, uma por tipo de exame)

| Estado | Tipos |
|---|---|
| `low_sample` (<20 laudos — descrito, nunca generalizado) | **150** |
| `processed_unvalidated` (cobertura de conceito <50%) | 33 |
| `review_sample_pending` (extraído, aguarda revisão) | 27 |
| `validated_clinically` | **0** |

Esse é o retrato honesto: 150 dos 210 tipos são cauda longa com amostra
insuficiente para qualquer generalização estatística, e **nenhum** tipo
está validado clinicamente.

### 3.2 Associações

3.864 pares testados com Fisher exato bicaudal, razão de prevalências e
de chances com IC, lift e correção de Benjamini-Hochberg. **711**
sobrevivem simultaneamente a: q ≤ 0,05, suporte suficiente, ≥2 médicos e
não ser artefato estrutural.

As de maior efeito são clinicamente coerentes:

| Exame | Associação | n | P(B\|A) vs P(B\|¬A) | RP [IC95%] |
|---|---|---|---|---|
| TC_ENCEFALO | ateromatose ↔ calcificações | 113 | 0,98 vs 0,11 | 8,98 [4,46–18,08] |
| RM_COLUNA_LOMBAR | artrose facetária ↔ espondilodiscoartropatia | 41 | 0,98 vs 0,11 | 8,76 [7,10–10,82] |
| RM_SACROILIACAS | capsulites ↔ entesites | 42 | 0,88 vs 0,05 | 16,6 [5,50–50,3] |
| RM_COLUNA_CERVICAL | desidratação discal ↔ hipertrofia | 98 | 0,81 vs 0,06 | 13,1 [7,71–22,4] |

**Achado metodológico mais importante desta execução:** antes do
controle de viés, as associações de maior efeito **não eram clínicas**.
Eram artefato, por duas causas distintas:

1. **Legenda virando achado.** "Tipo de Hiperplasia ( Wasserman et al )"
   é linha de referência bibliográfica impressa no laudo. Virava
   "achado" e coocorria perfeitamente com outras linhas da mesma
   legenda. Filtrado na origem.
2. **Estrutura do laudo, não do paciente.** Em TC de coronárias cada
   vaso é descrito em sua própria frase com seu próprio grau — então os
   quatro graus de estenose coexistem em 146 laudos com P = 1,0 nos dois
   sentidos. Isso não é associação clínica: é a forma do laudo.
   Detectado por **travamento mútuo** (P(B|A) e P(A|B) ambos ≥ 0,98 com
   suporte alto) e reclassificado como
   `structural_or_template_artifact` — exposto, não descartado.

### 3.3 Corpo × impressão

564 achados analisados. **109 sinalizados** por aparecerem na impressão
com suporte fraco no corpo. Isso é padrão do corpus, **não regra
clínica**: um achado não levado à impressão pode ser decisão correta do
radiologista, não omissão.

### 3.4 Estilo por médico

Os 7 perfis diferem de forma mensurável em densidade de conceitos por
laudo, percentual de negação explícita, uso de normalidade declarada e
frequência de linguagem de incerteza. Isso sustenta a exigência de
**não misturar estilos automaticamente** na compilação.

Nenhum destes é o perfil Jefferson. Esse perfil só pode ser alimentado
por correções que você aprovar.

### 3.5 Cauda não modelada

3.148 termos fora do léxico: 168 de prioridade alta, 849 média, 2.131
baixa. Cada um com frequência, distribuição por exame, sinal
distribucional e **o motivo de não ter sido modelado**. É lacuna medida
e priorizada — não descartada.

---

## 4. O que esta execução NÃO estabelece

Esta lista tem o mesmo peso que as anteriores.

1. **Não existe recall clínico.** A "cobertura" de 53,2% mede apenas se
   a sentença gerou ao menos um conceito. Não mede se o conceito está
   certo, nem se algo foi perdido. Recall exige gabarito anotado por
   radiologista — a amostra estratificada de 210 sentenças (210
   pacientes distintos, sem vazamento) está gerada e aguardando sua
   anotação.
2. **Não existe precisão medida no corpus.** O eval adversarial acertou
   26/26, mas são casos que eu mesmo construí com gabarito meu: mede
   não-regressão do motor, não desempenho no corpus real.
3. **Nenhuma associação é conhecimento médico.** São coocorrências
   documentadas, com denominador e limitação. Nenhuma foi validada
   contra guideline ou literatura primária — a validação canônica
   (seção 15) permanece `medical_review_required`, e eu não gerei
   citação de fonte que não pudesse abrir.
4. **Medidas quase não vinculam a conceitos** (0,3%), embora o motor
   detecte 6.890 medidas no corpus. A medida costuma estar em cláusula
   diferente do termo do achado. Limitação conhecida, registrada.
5. **150 dos 210 tipos têm amostra insuficiente.** Estão descritos, não
   generalizados.
6. **O escopo de negação é heurística de pontuação**, não parser
   sintático. Coordenação sem vírgula entre duas estruturas ainda pode
   misturar polaridade.
7. **O laudador (Fase 6) continua cobrindo só RM de joelho.** A camada
   universal alimenta a análise; o compilador ainda não foi reconstruído
   sobre ela.
8. **Este corpus contém laudos, não imagens.** Permite aprender
   linguagem, estrutura e relações documentadas. Não permite medir
   sensibilidade diagnóstica nem capacidade de interpretar exames.

---

## 5. Próximos passos, em ordem de valor

1. **Anotar a amostra estratificada** (`data/derived/eval/EVAL_SAMPLE_FOR_ANNOTATION.json`).
   É o bloqueio de tudo: sem ela não há precisão nem recall, e nenhuma
   regra pode ser promovida para o compilador.
2. **Revisar a cauda de prioridade alta** (168 termos) — é o caminho mais
   curto para aumentar cobertura real nos 33 tipos com cobertura baixa.
3. **Vincular medidas a conceitos** através de cláusulas adjacentes.
4. **Reconstruir o compilador sobre a camada universal**, com os gates
   da seção 17 (sem técnica por frequência, sem normalidade global, sem
   mistura de lados ou de médicos, bloqueio de contradição crítica).
5. **Validação canônica** dos padrões de maior impacto, com fonte
   primária verificável.
