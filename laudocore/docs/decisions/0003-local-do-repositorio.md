# ADR 0003 — LaudoCore como subpasta isolada em `verorad`, não novo repositório

**Status:** aceito, reversível

## Contexto

Esta sessão de trabalho foi provisionada com acesso apenas ao repositório
`JeffersonbragaRX/verorad`. A inspeção do repositório mostrou que ele já
contém um produto em produção, sem relação com o LaudoCore: um estimador
de idade óssea (ConvNeXtV2 exportado para ONNX, servido por um app
Streamlit em `app.py`/`atlas.py`/`preprocess.py`/`train.py`/
`export_onnx.py` na raiz, com pesos hospedados no Hugging Face). O
LaudoCore (laudos radiológicos gerais, corpus textual, retrieval, LLM
controlado) é um produto conceitualmente distinto.

Duas opções foram consideradas:

1. Criar um repositório GitHub novo e dedicado ao LaudoCore.
2. Colocar o LaudoCore em uma subpasta isolada (`laudocore/`) dentro do
   `verorad`, sem tocar nos arquivos existentes na raiz.

A opção 1 é arquiteturalmente mais limpa a longo prazo (deploys, CI e
histórico de commits separados), mas é uma ação visível externamente
(criação de um novo repositório sob a conta do usuário) e este ambiente
de execução está escopado apenas ao `verorad` — criar e popular um novo
repositório exigiria uma etapa de confirmação e configuração adicional
fora do fluxo desta tarefa.

## Decisão

Usar a opção 2 nesta rodada: todo o código e documentação do LaudoCore
vive em `laudocore/` na raiz de `verorad`, na branch designada para esta
tarefa. Nenhum arquivo pré-existente do estimador de idade óssea foi
modificado, movido ou removido.

## Consequência / como reverter

Se o usuário preferir um repositório dedicado, a migração é mecânica:
`git subtree split` (ou simplesmente copiar a pasta) de `laudocore/` para
um repositório novo, preservando ou não o histórico conforme preferência.
Nenhum dado sensível está em risco nessa migração porque `data/raw/` já
não é versionado (ADR 0002). Esta decisão deve ser revisitada antes da
Fase 8 (UI) ou de qualquer deploy, já que rodar dois produtos distintos a
partir do mesmo repositório pode complicar pipelines de deploy
específicos do Streamlit app existente.
