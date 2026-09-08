# ADR 0009 — Stack da interface final e integração num único processo

**Status:** aceito

## Contexto

A especificação mestra original sugeria Next.js/React/TypeScript/
Tailwind/shadcn para o frontend. Esta fase precisava entregar uma
interface final, funcional, integrada aos dados reais — não uma
demonstração.

## Decisões

1. **Vite em vez de Next.js.** Este é um app interno de página única,
   sem necessidade de SSR, rotas de servidor ou geração estática — Next
   adicionaria complexidade de build sem benefício correspondente para
   um usuário único rodando localmente. Vite + React + TypeScript +
   Tailwind (v4, via plugin oficial) entrega o mesmo padrão de
   componentização e o mesmo resultado visual com uma cadeia de build
   mais simples de manter por quem não é desenvolvedor web full-time.
2. **Sem biblioteca de componentes (shadcn ou outra).** Os primitivos
   de UI (`frontend/src/components/ui.tsx`) foram escritos à mão —
   poucos componentes, uso concentrado, e evita uma dependência de
   build adicional (shadcn exige um passo de instalação de componentes
   por arquivo) para um conjunto de telas que não justifica isso ainda.
3. **FastAPI servindo o build estático do frontend num único processo**
   (`backend/api/app.py`), em vez de dois serviços separados em
   produção. `run.sh` builda a interface uma vez e sobe tudo em
   `http://localhost:8000` com um comando — importante para um usuário
   que não é desenvolvedor: nada de gerenciar dois terminais/portas.
   Em desenvolvimento, o proxy do Vite (`vite.config.ts`) ainda permite
   rodar a interface com hot-reload separadamente, apontando para a API
   em `:8000`.

## Dois bugs de integração reais, encontrados testando a aplicação completa (não em testes unitários)

1. **SQLite entre threads.** FastAPI executa dependências síncronas
   (como `get_db`) numa threadpool; o setup e o teardown de uma
   dependência-generator podem ser despachados em threads diferentes
   entre si. SQLite proíbe isso por padrão
   (`SQLite objects created in a thread can only be used in that same
   thread`) — toda rota retornava 500 na primeira navegação real pela
   interface. Corrigido com `check_same_thread=False` em
   `backend/api/db.py` (seguro aqui porque cada request tem sua própria
   conexão, nunca compartilhada entre requests).
2. **Fallback de SPA incompleto.** `StaticFiles(html=True)` só serve
   `index.html` para a raiz e arquivos que existem de fato — uma rota
   client-side como `/biblioteca/12` não é um arquivo, e recarregar a
   página nela devolvia 404. Um catch-all ingênuo resolveria isso, mas
   criava um bug pior: uma rota `/api/*` que não bateu em nenhum router
   também cairia nesse catch-all e devolveria 200 com HTML em vez de
   404, escondendo silenciosamente um erro real de API atrás de uma
   resposta aparentemente bem-sucedida. Corrigido em
   `backend/api/app.py` com um catch-all que primeiro verifica se o
   caminho começa com `api/` (nesse caso, 404 de verdade) antes de
   cair no `index.html`.

Ambos têm teste de regressão (`tests/test_api.py::TestConnectionCrossThreadSafety`
e `::TestSpaFallback`) e foram confirmados corrigidos rodando a
aplicação de ponta a ponta via Playwright antes do commit — ver
`scripts/e2e_smoke_test.py` e ADR geral de metodologia na seção
"mini-eval" (0007): bugs de integração real, mais uma vez, só
apareceram testando o sistema completo, não os componentes isolados.
