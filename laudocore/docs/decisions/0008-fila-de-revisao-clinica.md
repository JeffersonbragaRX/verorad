# ADR 0008 — Fila de revisão clínica para ambiguidade genuína

**Status:** aceito

## Contexto

O usuário determinou uma regra explícita: quando existe ambiguidade
clínica real, o sistema não deve forçar uma classificação artificial —
deve preservar o texto original, aplicar a interpretação mais
conservadora e registrar o caso numa fila de revisão final, com trecho
original, saída produzida, regra aplicada, motivo da dúvida e risco
clínico.

## Decisão

Nova tabela `clinical_review_queue` (`backend/db/schema.py`), populada
por `backend/clinical/review_queue.py::detect_ambiguities()` a cada
execução de `scripts/extract_concepts.py`. Quatro critérios de
ambiguidade, todos com evidência real no corpus (não especulados):

| Motivo | Risco | Critério |
|---|---|---|
| `post_surgical_context` | alto | Sentença menciona reconstrução/enxerto/meniscectomia — o achado extraído pode se referir à estrutura nativa OU ao material cirúrgico; o extrator não distingue os dois casos. |
| `hedge_language` | médio (achado positivo) / baixo (achado negativo) | Linguagem de incerteza diagnóstica no próprio texto original (`sugestivo de`, `não se pode excluir`...). |
| `multiple_measurements` | baixo | Mais de uma medida em cm na mesma sentença — não é seguro assumir qual corresponde ao achado. |
| `grade_range_overflow` | baixo | Faixa de grau com 3+ valores — o parser de grau só captura os dois primeiros. |
| `unmatched_header` | médio | Cabeçalho de seção não reconhecido pelo parser da Fase 1 (herdado de `report_sections.unmatched_header`). |

Resultado no corpus real: **163 itens pendentes** — 89 alto risco
(contexto pós-cirúrgico), 50 médio, 24 baixo. Nenhum desses itens teve
classificação forçada: os conceitos continuam sendo extraídos
normalmente (o texto real muitas vezes contém achados genuínos), mas
ficam adicionalmente sinalizados para revisão humana antes de qualquer
uso em um laudo real.

## Persistência que sobrevive a reprocessamento (mudança de arquitetura em relação à ADR 0004)

A ADR 0004 já havia previsto que o padrão "recriar tudo a cada
execução" precisaria mudar quando anotações humanas passassem a se
anexar a linhas específicas — este é esse momento. `clinical_review_queue`
usa **UPSERT por chave natural** `(sentence_id, reason)`
(`sync_review_queue()`): reexecutar a extração atualiza o conteúdo
extraído mas **preserva** `status`/`reviewer_note`/`resolved_at` de
itens já revisados por um humano. Itens que deixam de ser ambíguos
(por exemplo, um bug de extração corrigido) são removidos
automaticamente na sincronização seguinte — comportamento verificado
por teste de integração
(`tests/test_review_queue_integration.py`), que roda a extração duas
vezes, marca um item como resolvido manualmente, reexecuta e confirma
que o status sobrevive.

## Uso pretendido

Esta tabela é a fonte de dados da tela "Fila de Revisão Clínica" na
interface (Fase 8) — cada item mostra trecho original, saída do
sistema, regra aplicada, motivo e risco, com ação de marcar como
revisado (com nota opcional). A fila **não é commitada** no Git (contém
texto real de sentença — mesma regra da ADR 0002); só o agregado por
motivo/risco entra em `QA_REPORT_FASE4.json`.
