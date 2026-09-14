# LaudoCore

Duas coisas, deliberadamente separadas:

1. **Mineração clínica do corpus inteiro** — 8.402 laudos reais (RM, TC,
   RX), 210 tipos de exame, 10 domínios, 7 médicos. Extração de
   conceitos clínicos estruturados por regras, com proveniência e
   estatística de associação. É o que a V2 construiu.
2. **Laudador assistido (piloto)** — compila laudo reusando frase real
   do corpus. Cobre **apenas RM de joelho**, não os 210 tipos.

**Sem LLM em nenhuma etapa.** Nada é gerado livremente: o sistema extrai
por regras determinísticas, escolhe entre frases que médicos reais
escreveram, ou sinaliza que não sabe.

**Nada aqui está validado clinicamente.** Todo conceito, associação e
candidato a normalidade está em `extraction_candidate` / `corpus_only`.
A promoção para validado depende de revisão médica.

Este diretório vive dentro do repositório `verorad`, que também contém
um produto não relacionado (estimador de idade óssea) — ver
`docs/decisions/0003-local-do-repositorio.md`.

---

## Rodar

Pré-requisitos: **Python 3.11+** e **Node.js 18+**. O corpus precisa
estar em `data/raw/` (fora do Git — ver ADR 0002). Nada sai da máquina.

### Linux / macOS

```bash
# uma vez — processa o corpus inteiro (leva ~1 minuto no total)
python3 scripts/ingest_corpus.py         # 8.402 laudos -> SQLite
python3 scripts/mine_clinical_layer.py   # léxico + 99.921 conceitos
python3 scripts/analyze_clinical_corpus.py  # associações, perfis, artefatos
python3 scripts/run_clinical_eval.py     # eval + amostra para anotação

# a cada uso
./run.sh
```

### Windows

Não use `run.sh` (é bash). No PowerShell, a partir da pasta `laudocore`:

```powershell
# uma vez
py -m pip install -r requirements.txt
py scripts\ingest_corpus.py
py scripts\mine_clinical_layer.py
py scripts\analyze_clinical_corpus.py
py scripts\run_clinical_eval.py

cd frontend
npm install
npm run build
cd ..

# a cada uso
py -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

Abra `http://localhost:8000`.

Se o PowerShell não reconhecer `py`, use `python`. Se a interface abrir
em branco, confirme que `frontend\dist\index.html` existe — sem o build
a API sobe, mas não há o que servir.

---

## O que existe hoje

| Camada | Descrição |
|---|---|
| **Dados** | 8.402 laudos, 5.701 pacientes, 170.418 sentenças, 210 tipos de exame, 7 médicos |
| **Parser global** | Seções e sentenças em RM/TC/RX; cabeçalho desconhecido nunca reclassifica o laudo (ADR 0011) |
| **Clause Engine** | Escopo de negação, certeza, lateralidade, medida, grau, temporalidade — por posição da menção, agnóstico de domínio |
| **Léxico** | 6.247 termos minerados do corpus, com método e evidência por termo |
| **Conceitos** | 99.921 conceitos nos 210 tipos, com proveniência completa |
| **Análise** | Associações com Fisher/IC/FDR, perfis por exame e por médico, corpo × impressão, longitudinal, cauda priorizada |
| **Interface** | 6 telas de análise + 3 do laudador piloto |
| **Compilador (piloto)** | Monta laudo de RM de joelho reusando frase real, com bloqueios de segurança |

### Telas

**Análise do corpus** — Visão geral · Cobertura (matriz por tipo de
exame com estado de validação) · Conceitos (com sentença de origem) ·
Associações (com denominador, IC, q e interpretação permitida) · Médicos
· Cauda não modelada.

**Laudagem (piloto: RM joelho)** — Biblioteca · Novo laudo · Fila de
revisão.

---

## Arquitetura

```text
data/raw/ (corpus, fora do git)
  → backend/normalization  (RAW → clean → normalized, hashes)
  → backend/parsers        (seções e sentenças, todas as modalidades)
  → backend/clinical       clause_engine → lexicon → concept_layer
  → backend/analysis       estatística de associação (stdlib puro)
  → backend/compiler       banco de frases + montagem (piloto: joelho)
  → backend/api            FastAPI — sem mock, tudo do SQLite real
  → frontend/              React + Vite + TypeScript + Tailwind
```

Decisões técnicas: `docs/decisions/0001` a `0011`. A **0011** documenta
a arquitetura da mineração global e as hipóteses que foram testadas e
descartadas; a **0010**, a rodada de correção pós-auditoria externa.

Relatórios: `docs/CLINICAL_MINING_REPORT.md` (o que os dados mostram e o
que não foi estabelecido) e `docs/IMPLEMENTATION_TRACEABILITY.md` (item
a item do que foi pedido × o que existe).

---

## Testes

```bash
python3 -m unittest discover -s tests -v   # 212 testes
cd frontend && npm run build                # typecheck + build
python3 scripts/e2e_smoke_test.py           # fluxo do laudador num navegador real
```

---

## Limitações conhecidas

- **Não existe recall nem precisão clínica.** A "cobertura" de 53,2% é
  superficial: mede se a sentença gerou ao menos um conceito, não se o
  conceito está certo. A amostra estratificada de 210 sentenças está
  gerada e aguarda anotação médica — é o bloqueio de tudo.
- **150 dos 210 tipos de exame têm amostra pequena** (<20 laudos).
  Descritos, nunca generalizados.
- **Nenhuma associação é conhecimento médico.** São coocorrências
  documentadas, com denominador e limitação. Validação canônica contra
  guideline não foi feita.
- **Medidas vinculam a apenas 0,3% dos conceitos**, embora 6.890 sejam
  detectadas no corpus — a medida costuma estar em cláusula diferente do
  achado.
- **Escopo de negação é heurística de pontuação**, não parser sintático.
- **O laudador cobre só RM de joelho.** A camada universal alimenta a
  análise; o compilador ainda não foi reconstruído sobre ela.
- **Reuso de frase não garante conteúdo exato**: uma frase real pode
  dizer mais do que o conceito capturou (ADR 0006).
- **Este corpus tem laudos, não imagens.** Permite aprender linguagem e
  relações documentadas; não permite medir acurácia diagnóstica.
- Todo laudo compilado é **rascunho** e exige revisão médica integral.

---

## Próximo passo

Anotar `data/derived/eval/EVAL_SAMPLE_FOR_ANNOTATION.json`. Sem essa
anotação não há métrica clínica e nenhuma regra pode ser promovida.
