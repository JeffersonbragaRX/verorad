# ADR 0005 — Clinical Concept Layer por regras (sem LLM) na Fase 4

**Status:** aceito

## Contexto

A ESPECIFICACAO_MESTRA (seção 20) proíbe que o LLM seja fonte única de
verdade clínica e exige que toda inferência clínica automática tenha
origem e nível de confiança rastreáveis. A Fase 4 (Clinical Concept
Layer) precisa transformar as 18.597 sentenças de achados/impressão do
vertical de joelho em achados estruturados (estrutura, achado, status,
gravidade, localização) para alimentar futuramente o Report Compiler e
o auditor determinístico.

## Decisão

Implementar a extração por regras/regex (`backend/clinical/knee_concepts.py`),
sem qualquer chamada a LLM. Cada conceito extraído carrega `rule_id`,
permitindo auditar exatamente qual regra o gerou. O vocabulário de
estruturas (menisco, LCA/LCP, colaterais, compartimentos condrais,
derrame, cistos, edema ósseo, tendinopatia) foi levantado por
frequência real nas sentenças do vertical antes de virar regra — não
foi assumido de livro-texto (ver `docs/data_dictionary.md`, seção
"Vocabulário clínico do joelho").

## Limitações conhecidas e reconhecidas explicitamente

1. **Cobertura (recall) atual: 56,7%** das sentenças de achados/impressão
   produzem pelo menos um conceito. As 43,3% restantes descrevem
   achados reais (cauda longa: perimeniscite, ectasia venosa, corpos
   livres, edema da gordura de Hoffa, peritendinite anserina, tróclea
   isolada sem grau, superfícies condrais genéricas) para os quais
   ainda não há extrator dedicado — não foram "perdidos" por erro, e
   sim conscientemente deixados fora do escopo do v0.
2. **Não há ainda um conjunto de avaliação anotado manualmente**
   (gold standard). A métrica de cobertura mede apenas presença de
   >=1 conceito por sentença — isso é uma aproximação de recall, **não
   é uma medida de precisão**. Não afirmamos que os conceitos
   extraídos estão clinicamente corretos sem revisão humana.
3. Durante o desenvolvimento, uma revisão manual de amostra (30
   sentenças com conceito + 30 sem) encontrou e corrigiu 1 bug real de
   precisão: "patela" é prefixo textual de "patelar", e um match por
   substring simples atribuía ao osso patela um achado que era do
   tendão patelar (`tendões do quadríceps e patelar preservados` →
   corrigido para exigir fronteira de palavra). Ver
   `tests/test_knee_concepts.py::TestPatellaWordBoundaryBug` para o
   teste de regressão.
4. A amostra de revisão manual (`FASE4_manual_review_sample.json`)
   contém texto real de sentença e **não é commitada** — mesma regra
   da ADR 0002.

## Próximo passo recomendado antes de confiar nesta camada em produção

Construir um conjunto de avaliação pequeno (50-100 sentenças)
anotado manualmente por um radiologista (idealmente o próprio usuário,
dada a subespecialidade em MSK) com o conceito "correto" esperado, e
medir precisão/recall reais contra esse gold standard — nos moldes da
Fase 28 (Evals) da especificação, mas em escala reduzida e focada
neste vertical.
