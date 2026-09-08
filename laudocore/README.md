# LaudoCore (provisório)

Laudador radiológico assistido — vertical piloto: **RM de joelho**
(`RM_JOELHO_D` / `RM_JOELHO_E`). Corpus real → regras determinísticas
→ reuso de frase real → interface. **Sem LLM em nenhuma etapa desta
entrega** — nenhum texto é gerado livremente; o sistema escolhe entre
frases que médicos reais já escreveram, ou sinaliza que não sabe.

Este diretório vive dentro do repositório `verorad`, que também contém
um produto não relacionado (estimador de idade óssea) — ver
`docs/decisions/0003-local-do-repositorio.md`.

## Rodar

```bash
# uma vez, com o corpus em data/raw/ (fora do git — ver ADR 0002):
python3 scripts/ingest_vertical.py
python3 scripts/extract_concepts.py

# a cada uso:
./run.sh
```

Abra `http://localhost:8000`. `run.sh` instala dependências na
primeira vez, builda a interface e sobe tudo (API + interface) num
único processo. Sem internet exigida em tempo de execução.

Requisitos: Python 3.11+, Node.js 18+. Nada além disso — todo o
armazenamento é local (SQLite em `data/processed/laudocore.db`, fora
do Git).

## O que existe hoje

| Camada | Descrição |
|---|---|
| **Dados** | 911 laudos reais (4 médicos), auditados linha a linha (Fase 0) |
| **Extração** | 20.498 sentenças → 15.275 conceitos clínicos estruturados, por regras (sem LLM) |
| **Compilador** | Monta laudo a partir de achados escolhidos, reusando frase real do corpus |
| **Fila de revisão** | 163 casos de ambiguidade genuína, sinalizados — nunca decididos por adivinhação |
| **Interface** | Dashboard, Biblioteca, Novo Laudo, Fila de Revisão — integrada aos dados reais |

Quatro telas, todas puxando dados reais via API (nenhum dado mockado):

- **Dashboard** — contagens do vertical e fila de revisão por risco.
- **Biblioteca** — busca/filtra os 911 laudos reais; texto original ao
  lado da classificação extraída, sentença por sentença.
- **Novo laudo** — fluxo principal: busca achados reais (todas as
  combinações já observadas no corpus, com frequência), compila um
  laudo reusando frases reais, mostra avisos de conflito/duplicidade e
  rastreabilidade (frase → médico de origem), copia ou exporta `.txt`.
- **Fila de revisão clínica** — casos de ambiguidade genuína (contexto
  pós-cirúrgico, linguagem de incerteza, medidas múltiplas...), com
  ação de marcar como revisado.

## Arquitetura

```text
data/raw/ (corpus, fora do git)
  → backend/normalization  (RAW → clean → normalized)
  → backend/parsers        (seções, sentenças — orientado por médico real)
  → backend/clinical       (extração de conceitos por regras + fila de ambiguidade)
  → backend/compiler       (banco de frases reais + montagem do laudo)
  → backend/api            (FastAPI — nenhum mock, tudo lê do SQLite real)
  → frontend/              (React + Vite + TypeScript + Tailwind)
```

Detalhes e decisões técnicas: `docs/architecture.md` e
`docs/decisions/0001` a `0009` (uma por decisão relevante — motivo,
alternativas consideradas, consequência).

## Testes

```bash
python3 -m unittest discover -s tests -v   # 133 testes (backend + API)
cd frontend && npm run build                # typecheck + build da interface
python3 scripts/e2e_smoke_test.py           # fluxo completo num navegador real
```

## Limitações conhecidas (honestas, não escondidas)

- **Escopo**: só RM de joelho. Generalizar para os outros 209
  `exam_type` do corpus é trabalho novo, não uma extensão trivial.
- **Sem LLM**: o compilador só reusa frases já ditas por um médico real
  — não redige nada novo. Uma combinação de achados sem frase
  correspondente no corpus fica `unresolved`, nunca inventada.
- **Reuso de frase não é garantia de conteúdo exato**: uma frase real
  pode conter informação além do achado pedido, se a extração não
  capturou tudo o que a frase diz (recall ~58%). Ver ADR 0006.
- **Fidelidade textual ≠ correção clínica**: a extração foi validada
  por leitura sistemática (eu, não um radiologista) contra o texto —
  bate com o que a frase diz. Se é a forma clinicamente certa de
  descrever o achado, só um médico valida. Ver ADR 0007.
- **163 casos na fila de revisão**, a maioria (89) contexto
  pós-cirúrgico/reconstrução, onde o sistema não tenta adivinhar se um
  achado é da estrutura nativa ou do enxerto.
- Todo laudo compilado é **rascunho** — exige revisão médica integral
  antes de qualquer uso real.

## Próximo passo proposto

Validação clínica pelos olhos de um radiologista (agora prática de
fazer via a interface, não mais via JSON), e/ou generalizar o pipeline
para um segundo vertical (ex.: RM de ombro) para testar se a
arquitetura escala sem recomeçar do zero.
