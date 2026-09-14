# ADR 0011 — Mineração clínica global: arquitetura da V2

**Status:** aceito

## Contexto

O projeto vinha de um vertical piloto (RM de joelho, 911 de 8.402
laudos, 4 de 7 médicos). O PROMPT MESTRE V2 exigiu o inverso:
compreender clinicamente o corpus **inteiro** — 210 tipos de exame, 10
domínios, 3 modalidades — sem reduzir escopo a um exame.

A implementação anterior não era generalizável por construção: o parser
de seções e o extrator de conceitos tinham vocabulário hand-coded de
joelho.

## Decisão 1 — Cabeçalho desconhecido não troca o tipo da seção

Medido sobre o corpus inteiro, o parser calibrado em joelho deixava
**96,2% dos RX sem nenhuma seção de achados**. A causa não era falta de
vocabulário: um cabeçalho desconhecido reclassificava todo o resto do
laudo como `other`.

Um rótulo que o parser não conhece passa a criar uma **subseção da seção
corrente**, sem alterar o tipo. O pior caso vira "rótulo desconhecido"
em vez de "achados viraram outra coisa".

Consequência: RX 95,3% → 0,3% de cabeçalho não reconhecido; sem seção de
achados 96,2% → 0,6%.

## Decisão 2 — Achados implícitos marcados como implícitos

RX não usa `RELATÓRIO:`; abre os achados com frase-guia ("As
radiografias digitais ... mostram:"). Reconhecer isso é necessário, mas
apresentá-lo como se houvesse cabeçalho explícito seria falsear a
estrutura. Os dois casos ficam marcados (`implicit_lead_in`,
`implicit_no_header`) e contáveis no QA.

## Decisão 3 — Clause engine agnóstico de domínio, não regras por exame

Escrever um extrator por tipo de exame seriam 210 extratores; o de
joelho sozinho consumiu uma sessão inteira e chegou a 58% de cobertura
superficial. A alternativa adotada separa **mecanismo** de
**vocabulário**:

- mecanismo: adaptação do padrão NegEx/ConText ao português — cue com
  posição, direção e escopo terminado por marcador de fronteira;
  consultas por posição da menção;
- vocabulário: minerado do próprio corpus.

Isto é uma adaptação própria, **não** uma implementação validada de
ConText para português. A validação é a suíte adversarial, não uma
publicação.

## Decisão 4 — Léxico minerado, com método registrado por termo

Cada termo carrega o método que sustenta sua classe:

| Método | Força |
|---|---|
| `corpus_positional` | estatística medida (P de vir após preposição, após "sinais de") |
| `morphological` | sufixo regular do português médico (-patia, -ite, -ose) |
| `model_knowledge` | inferência do modelo — pendente de revisão |

Duas hipóteses foram testadas **antes** de virar código e uma foi
descartada:

- **Descartada:** concentração por `exam_type` separaria anatomia de
  achado. Não separa — separa vocabulário específico-de-exame
  ("abaulamento discal" e "redução luminal" são achados concentrados).
- **Aceita com ressalva:** P(precedido de preposição) identifica
  anatomia bem; início de cláusula não separa nada, porque em português
  tanto "Rins" quanto "Condropatia" abrem frase. O segundo sinal ficou
  registrado como evidência, não como critério.

## Decisão 5 — Núcleo do termo é a primeira palavra

Em português o substantivo precede o adjetivo: o núcleo de "abaulamento
discal" é *abaulamento*. A regra do inglês (última palavra) deixava
justamente os compostos mais frequentes sem classe — findings foram de
350 para 693 termos ao corrigir. É bug de linguagem, não lacuna de
cobertura.

## Decisão 6 — Severidade, morfologia e distribuição são eixos separados

Colapsados num campo único, "bilateral" (lateralidade) e "parcial"
(extensão) caíam no campo de gravidade. O schema universal já os trata
como campos distintos; o extrator passou a respeitar isso.

## Decisão 7 — Artefato de template é detectado e exposto, não descartado

Antes do controle, as associações de maior efeito não eram clínicas.
Duas causas:

1. linha de legenda ("Tipo de Hiperplasia ( Wasserman et al )") virando
   achado — filtrada na origem;
2. estrutura do laudo: em TC de coronárias cada vaso tem seu grau, então
   os quatro graus coexistem com P = 1,0 nos dois sentidos.

A segunda é detectada por **travamento mútuo** (P(B|A) e P(A|B) ambos
≥ 0,98 com suporte alto) e reclassificada como
`structural_or_template_artifact`. Exposta, não removida: a
especificação exige distinguir associação de achados de associação
decorrente do template, e remover em silêncio esconderia a distinção.

## Decisão 8 — Camada universal convive com a legada, separada e rotulada

`clinical_concepts_universal` (210 tipos, léxico minerado) e
`clinical_concepts` (joelho, hand-coded) permanecem tabelas distintas.
Unir por conveniência misturaria vocabulários de qualidade diferente. A
navegação da interface separa "Análise do corpus" de "Laudagem (piloto:
RM joelho)" pelo mesmo motivo.

## Decisão 9 — Estatística em stdlib, validada contra referência

Sem scipy no ambiente. Fisher exato bicaudal, IC de Woolf, razão de
prevalências e Benjamini-Hochberg implementados em stdlib e validados
contra um valor canônico (lady tasting tea, p = 2/70), não por
plausibilidade.

Decisão associada: **p-valor nunca sai sozinho**. Toda associação carrega
denominador, tamanho de efeito, IC, n de pacientes, n de médicos e uma
frase de interpretação permitida que nega causalidade.

## Consequências

- 8.402 laudos, 170.418 sentenças, 99.921 conceitos, 210 tipos cobertos.
- 212 testes.
- Zero itens `validated_clinically` — e isso é o resultado correto.
- O compilador (Fase 6) **não** foi reconstruído sobre a camada
  universal; continua cobrindo só RM de joelho. Está declarado em
  `IMPLEMENTATION_TRACEABILITY.md`, não escondido.
