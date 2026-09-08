# ADR 0007 — Mini-eval de fidelidade textual (Fase 4 + Fase 6)

**Status:** aceito

## Contexto

As ADRs 0005 e 0006 recomendavam um conjunto de avaliação anotado
manualmente antes de considerar a extração de conceitos (Fase 4) e o
Report Compiler (Fase 6) confiáveis além de rascunho. Esta rodada
executa essa avaliação.

## Metodologia e seu limite epistêmico (importante)

A amostragem foi estratificada por `rule_id` (2 exemplos por regra
quando havia ≥10 ocorrências, até 3 quando havia menos), cobrindo as
43 regras de extração distintas — 86 sentenças reais no total,
mantidas apenas localmente (`data/derived/qa/`, fora do Git, mesma
regra da ADR 0002).

**Quem avaliou fui eu (Claude), não um radiologista.** O que eu posso
julgar de forma defensável é **fidelidade textual**: o conceito
extraído representa exatamente o que a frase, lida literalmente, diz —
nem mais, nem menos? O que eu **não posso** julgar é correção clínica
no sentido pleno (por exemplo, se "amputação da margem livre" deveria
mesmo ser classificado como `finding=tear` do ponto de vista de um
radiologista musculoesquelético, ou se seria mais preciso um rótulo
diferente). Este documento não substitui uma revisão por um médico —
é uma camada de verificação mais barata e imediata (consistência entre
texto e estrutura extraída), que pode e deve ser complementada por
revisão clínica do usuário antes de qualquer uso real.

## Resultado: 4 bugs de precisão reais encontrados e corrigidos

1. **`verticalizado` sozinho não implica degeneração.** O extrator de
   ligamentos cruzados tratava "verticalizado" como sinônimo de
   degeneração. A frase real "Ligamento cruzado posterior
   verticalizado, porém íntegro." (25 ocorrências no corpus) não
   contém a palavra "degeneração" em lugar nenhum, mas era marcada como
   `degeneration=present`. Corrigido removendo "verticalizad" da lista
   de palavras-chave de degeneração — verticalização sem outra palavra
   de degeneração agora fica corretamente sem esse conceito.

2. **"Praticamente completa" não é "completa".** "Rotura praticamente
   completa do ligamento cruzado anterior" (17 ocorrências no corpus)
   era relatada com `severity=complete`, superestimando a gravidade.
   Corrigido com uma checagem explícita de qualificadores de
   aproximação ("praticamente completa", "quase completa"), agora
   reportados como `severity=near_complete`.

3. **Compartimento específico duplicado como "não especificado".**
   "Condropatia femorotibial medial." (12 ocorrências) gerava DOIS
   conceitos: um correto (`location=medial_femorotibial`) e um
   redundante (`location=femorotibial_unspecified`), porque
   "femorotibial" é substring de "femorotibial medial". Corrigido
   descartando o genérico quando o específico da mesma família já foi
   encontrado na mesma sentença.

4. **Ligamentos colaterais: espessamento/degeneração intersticial
   suprimidos quando a rotura era negada.** "Espessamento cicatricial
   do ligamento colateral medial, sem roturas." e "Degeneração
   intersticial das fibras... sem sinais de ruptura." (achados crônicos
   reais, afirmados pela frase) eram classificados como
   `injury=absent`, porque só a rotura aguda foi negada — o
   espessamento/degeneração real ficava suprimido. Mesma classe de bug
   já corrigida para menisco e ligamentos cruzados (ADR 0006), agora
   também aplicada a `_extract_collateral_ligaments`. Duas frases reais
   confirmaram o padrão de forma independente na amostra.

Um quinto problema menor (não um bug de precisão, mas de
completude/duplicação): a lista de sinônimos de cisto tinha "cisto
gangliônico" repetido duas vezes, gerando 2 conceitos idênticos para a
mesma menção; e a gravidade de cistos ("pequeno cisto poplíteo") não
era capturada apesar de estar explícita no texto. Ambos corrigidos.

Todos os 4 bugs têm teste de regressão em `tests/test_knee_concepts.py`
e foram confirmados corrigidos contra o corpus real (não apenas contra
o teste sintético) antes deste commit.

## Resultado agregado após as correções

- Conceitos extraídos: 14.798 → 14.675 (queda esperada — remoção de
  concepts espúrios/duplicados é o resultado correto, não uma perda)
- Cobertura (recall aproximado): 56,7% → 56,7% (praticamente
  inalterada — as correções mudaram a QUALIDADE dos conceitos
  existentes, não a quantidade de sentenças cobertas)
- 74 testes automatizados passando (11 novos desta rodada)

## Limitações que permanecem, documentadas e não corrigidas nesta rodada

Recall gaps encontrados na mesma amostra, categoria mais branda de erro
(informação omitida, não informação errada) — deixados como limitação
conhecida em vez de perseguidos um a um:

- Variantes com hífen/acento não reconhecidas ("tíbio-fibular" vs
  "tibiofibular", "patelo-femoral" vs "patelofemoral", "tróclea
  femoral" vs "troclear", "fêmorotibial" com circunflexo — provável
  erro de digitação na fonte).
- Faixas de grau ("grau I/II", "grau II/III") truncadas para o limite
  inferior apenas.
- Construções coordenadas com elisão que omitem uma estrutura
  ("Ligamento cruzado posterior e colateral lateral preservado." —
  extrai só o LCP, perde o LCL, que exige a palavra "ligamento"
  completa antes de "colateral lateral" para ser reconhecido).
- Achados adicionais em frases compostas não modelados por nenhuma
  regra (fissuras condrais sem a palavra "condropatia", fraturas por
  insuficiência, alterações pós-cirúrgicas/meniscectomia).

## Conclusão

A avaliação não confirma nem afasta a hipótese de que o compilador
esteja pronto para uso real — confirma que os componentes já
construídos ficaram mais fiéis ao texto de origem depois desta rodada,
e que o método (amostragem estratificada + leitura item a item) é
eficaz para achar bugs de precisão que os testes unitários sintéticos,
por não terem sido escritos a partir de casos reais adversos, não
pegavam. **A avaliação clínica de fato — se os rótulos e a estrutura
fazem sentido para um radiologista, não apenas se batem com o texto —
continua pendente e só o usuário pode fazer.**
