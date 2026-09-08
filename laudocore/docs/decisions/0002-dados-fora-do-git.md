# ADR 0002 — Corpus RAW mantido fora do controle de versão

**Status:** aceito

## Contexto

O corpus recebido (`data/raw/`) contém laudos radiológicos reais na
íntegra — `report_text` completo, `patient_id` pseudonimizado,
`exam_datetime`, idade, sexo e médico responsável. Ainda que o export
já remova nome, data de nascimento e identificadores de RIS/PACS
(SUID, Accession, Ticket), a combinação de `patient_id` + data/hora do
exame + médico é, em tese, suficiente para reidentificação cruzando com
a agenda do serviço. A especificação mestra do projeto (seção 30) exige
explicitamente desidentificação antes de qualquer envio externo e proíbe
expor o corpus fora do ambiente controlado.

## Decisão

`data/raw/`, `data/staging/`, `data/processed/` e qualquer derivado que
contenha `report_text` ou `patient_id` em texto claro **não são
versionados no Git** e, portanto, nunca são enviados ao GitHub — nem em
repositório privado. Apenas artefatos agregados/estatísticos
(`BASELINE_REPORT.md`, `QA_REPORT.json`, `exam_types.csv`,
`physicians.csv`, documentação) são commitados. Isso é reforçado por
`.gitignore` na raiz de `laudocore/`.

## Consequência

Qualquer pessoa clonando o repositório a partir do zero terá a
documentação e os scripts, mas precisará colocar o corpus manualmente em
`data/raw/` para reproduzir o baseline — isso é intencional. Fases
futuras que exigirem persistência (banco de dados, embeddings) devem
seguir a mesma regra: o banco/índice pode viver localmente ou em infra
controlada pelo usuário, nunca commitado como arquivo no repositório.
