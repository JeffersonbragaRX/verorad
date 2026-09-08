# ADR 0006 — Report Compiler por reuso de frase real (sem LLM), Fase 6

**Status:** aceito, com limitação estrutural reconhecida

## Contexto

A Fase 6 (Report Compiler) precisa montar um laudo a partir de achados
já decididos pelo médico (`FindingRequest`: estrutura, achado, status,
gravidade, localização), sem LLM nesta fase e sem inventar texto
(ESPECIFICACAO_MESTRA seção 20 e 21).

## Decisão

O compilador (`backend/compiler/report_compiler.py`) escolhe, para
cada achado solicitado, a frase REAL mais frequente no corpus que
descreve exatamente essa combinação (`backend/compiler/phrase_bank.py`,
uma versão mínima da biblioteca de frases da Fase 3, com proveniência
até o médico de origem). Nunca gera prosa — se não houver frase real
para a combinação pedida, o achado fica em `unresolved`, nunca é
preenchido com texto genérico.

## Bug de precisão encontrado e corrigido durante o desenvolvimento

Testando o compilador contra o corpus real, a combinação
`meniscus_lateral / tear / absent` foi resolvida com a frase
"Degeneração difusa do menisco lateral, sem roturas." — uma frase real,
mas que afirma algo (degeneração) **além** do que foi pedido (apenas
ausência de rotura). Investigando a causa raiz: o extrator da Fase 4
tratava "rotura" e "degeneração" como alternativas mutuamente
exclusivas (`if/elif`) por estrutura/sentença, quando na realidade são
dois eixos clínicos independentes — uma estrutura pode estar
degenerada E sem rotura ao mesmo tempo (achado real e frequente).

Corrigido em `backend/clinical/knee_concepts.py`
(`_extract_meniscus`, `_extract_cruciate_ligaments`): tear-status e
degeneração agora são emitidos como conceitos independentes. Isso fez
essas sentenças serem corretamente reclassificadas como "compostas"
(mais de um conceito), e o `PhraseBank` foi alterado para **preferir
frases "limpas"** (sentença de origem com exatamente 1 conceito no
total) sobre "compostas" ao escolher qual frase reutilizar — reduzindo
o risco de reuso injetar conteúdo clínico não solicitado. Coberto por
teste de regressão
(`tests/test_report_compiler.py::TestPhraseBankPrefersCleanSentences`).

Resultado prático: a extração de conceitos (Fase 4) passou de 13.665
para 14.798 conceitos (mais graus de liberdade capturados
corretamente), e o exemplo de demonstração do compilador passou a usar
"Menisco lateral de morfologia e aspecto preservados." em vez da frase
com degeneração não solicitada.

## Limitação estrutural que PERMANECE (não é possível eliminar nesta fase)

1. **"Limpa" (1 conceito) não é o mesmo que "sem conteúdo não capturado"**.
   A extração de conceitos (Fase 4) tem recall de ~57% — uma sentença
   pode ter exatamente 1 conceito tagueado e ainda conter prosa real
   não modelada por nenhuma regra. Exemplo real encontrado: "Ligamento
   cruzado posterior e colateral lateral preservado." — construção
   coordenada com elisão ("...e [ligamento] colateral lateral...") que
   o extrator de LCL não reconhece (exige a frase completa "ligamento
   colateral lateral"), então essa sentença é contada como "limpa" (só
   PCL) mas na verdade também descreve o LCL. Isto é uma lacuna de
   **recall** (informação omitida), não uma inconsistência de
   **precisão** (informação errada/atribuída à estrutura errada) — a
   categoria de erro mais perigosa clinicamente já foi tratada; esta
   categoria mais branda fica como limitação conhecida, não corrigida
   caso a caso indefinidamente.
2. Não há gold standard para medir precisão real do compilador (mesma
   ressalva da ADR 0005, agora também aplicada à escolha de frases).

## Consequência

**Todo laudo compilado por esta camada é um rascunho e exige revisão
integral do médico antes do uso** — não por formalidade, mas porque a
arquitetura desta fase (reuso literal de frase real, sem reescrita
controlada) estruturalmente não garante que a frase escolhida contém
exatamente e apenas o que foi pedido. Eliminar esse risco por completo
exigiria uma de duas mudanças maiores, fora do escopo desta fase:
(a) uma biblioteca de frases-modelo curtas e unitárias, curadas por um
médico, em vez de reuso de sentenças naturais completas; ou (b) uma
etapa de reescrita controlada por LLM cujo único papel seja *subtrair*
de uma frase real o que não foi pedido, nunca acrescentar — o que
reintroduziria LLM, mas em papel estreito e auditável, fora do escopo
atual (nenhuma IA generativa foi usada nesta fase).
