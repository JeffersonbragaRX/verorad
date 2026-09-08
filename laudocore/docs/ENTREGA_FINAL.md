# ENTREGA FINAL — LaudoCore (vertical piloto: RM de joelho)

Documento único que endereça, item a item, os critérios de conclusão
definidos para esta entrega. Gerado ao final da sessão de trabalho
autônomo que cobriu Fases 0, 1, 4, 6, mini-eval de fidelidade textual,
correções textuais adicionais, fila de revisão clínica, API e
interface final.

> **Nota posterior:** uma auditoria técnica externa encontrou 8 falhas
> reais adicionais no extrator e no compilador depois desta entrega
> (algumas bloqueantes para uso clínico), todas corrigidas numa rodada
> seguinte — ver `docs/decisions/0010-correcoes-pos-auditoria-externa.md`.
> Os números de conceitos/fila de revisão abaixo (15.275 / 163) são os
> desta entrega original; após a correção são 15.221 / 161 (ver ADR
> 0010 para a explicação da diferença). O restante deste documento fica
> como registro histórico da entrega original.

## 1. Fases previstas implementadas

Escopo redefinido logo no início (ver `docs/architecture.md`, seção
"Decisão de escopo"): em vez de generalizar para os 210 `exam_type` do
corpus de uma vez, o pipeline completo foi validado de ponta a ponta
num **único vertical** (RM de joelho, 911 laudos, 4 médicos) antes de
qualquer generalização — decisão tomada para evitar meses de andaime
sem nunca produzir um laudo utilizável.

Dentro desse vertical, todas as fases da especificação original que
fazem sentido sem LLM foram implementadas:

| Fase | Entregável | Status |
|---|---|---|
| 0 — Baseline | Auditoria do corpus completo (8.402 exames RM/TC/RX) | ✅ |
| 1 — Data Engine | Ingestão, normalização, seções, sentenças (vertical) | ✅ |
| 4 — Clinical Concept Layer | Extração de conceitos por regras | ✅ |
| 6 — Report Compiler | Montagem de laudo por reuso de frase real | ✅ |
| 7 — Auditor | Auditor determinístico leve embutido no compilador | ✅ (leve) |
| 8 — Interface | Dashboard, Biblioteca, Novo Laudo, Fila de Revisão | ✅ |
| 9 — Personalização | Preferência por médico no banco de frases | ✅ (parcial) |
| 2, 3, 5 — Taxonomia geral, biblioteca textual completa, retrieval híbrido | Não implementadas — dependem de generalizar além do vertical piloto | ❌ (fora do escopo desta entrega, ver seção 7) |
| 10, 11, 12 — Voz, RIS/PACS, fine-tuning | Explicitamente fora do escopo da V1 pela própria especificação original | ❌ (não pedido) |

Nenhuma etapa foi "implementada pela metade" silenciosamente — o que
não foi feito está listado explicitamente na seção 7, não omitido.

## 2. Interface moderna, branca, funcional e integrada

React + TypeScript + Vite + Tailwind v4, sem biblioteca de componentes
externa (ver ADR 0009 para a justificativa da escolha de stack).
Design: branco predominante, tons neutros, acento azul discreto,
bordas suaves, sombras mínimas, boa hierarquia visual, densidade
eficiente. Desktop-first, com adaptação responsiva testada em
viewport de tablet.

**Integrada de verdade, não uma camada visual**: as 4 telas (Dashboard,
Biblioteca, Novo Laudo, Fila de Revisão) leem e escrevem no banco de
dados real via API HTTP — nenhum dado mockado, verificado por
varredura de código (busca por `mock`/`fake`/`dummy`/dados hardcoded:
zero ocorrências fora de comentários que dizem explicitamente "sem
mock"). Capturas de tela e demonstração do fluxo real: seção 10.

Estados resolvidos em toda a aplicação: carregamento (skeletons),
vazio (com orientação do que fazer), erro (com botão de tentar de
novo), sucesso (toast). Atalhos de teclado: `/` foca a busca principal
de cada tela, `Ctrl/Cmd+Enter` compila o laudo.

## 3. Bugs textuais conhecidos corrigidos

Os quatro bugs textuais explicitamente apontados foram corrigidos, com
teste de regressão para cada um:

1. **Variantes de acento/hífen/grafia** (`tíbio-fibular` vs
   `tibiofibular`, `patelo-femoral`, `fêmorotibial`, `tróclea
   femoral`) — adicionadas como aliases reconhecidos em
   `backend/clinical/knee_concepts.py::_COMPARTMENTS`.
2. **Faixas de grau truncadas** (`grau I/II` virando só `grade_1`) —
   `_GRADE_RE` agora captura a faixa completa (`grade_1_2`), nunca só o
   limite inferior.
3. **Construções coordenadas com elisão** (`ligamento cruzado
   posterior e colateral lateral preservado` perdendo o LCL por
   completo) — resolvido de forma **geral**, não caso a caso: uma
   etapa de normalização textual (`_expand_elided_coordination`)
   reinsere o substantivo elidido antes da extração, cobrindo qualquer
   par entre as 4 frases de ligamento e os 2 tendões.
4. **Outros casos de perda/truncamento/duplicação encontrados durante
   a correção dos três acima**: fissura condral sem a palavra
   "condropatia" (não gerava conceito nenhum), fratura por
   insuficiência (descartada silenciosamente), duplicata de "cisto
   gangliônico" na lista de sinônimos (gerava 2 conceitos idênticos),
   gravidade de cisto não capturada, compartimento específico gerando
   um conceito redundante "não especificado" pela mesma menção — todos
   corrigidos.

Nos casos de **ambiguidade clínica real** (não um bug de parsing, mas
o texto genuinamente admitindo mais de uma leitura), a regra seguida
foi: não classificar, preservar o texto original, e registrar na fila
de revisão (seção 8) — nunca forçar uma interpretação. Ver ADR 0008.

## 4. Testes automatizados executados e aprovados

**133 testes automatizados** (`python3 -m unittest discover -s tests`),
todos passando no momento desta entrega — cobrindo normalização,
parser de seções/sentenças, extração de conceitos clínicos (39 casos,
15 de regressão de bugs reais), fila de revisão, compilador (13
casos), API (20 casos, incluindo os 2 bugs de integração da seção 9),
labels de exibição, e integração de ponta a ponta do pipeline de dados
(ingestão + extração + fila, com corpus real).

Frontend: `npm run build` (typecheck + build) limpo, sem erros; lint
(`oxlint`) com apenas 1 aviso estilístico sem impacto funcional.

## 5. Fluxo principal testado de ponta a ponta

`scripts/e2e_smoke_test.py`: sobe a API real servindo o build da
interface, abre num Chromium de verdade via Playwright, e valida com
asserções reais (não apenas capturas de tela): Dashboard mostra
contagens reais → Biblioteca carrega texto original + classificação →
Novo Laudo busca achado real, seleciona, compila e produz um laudo com
conteúdo genuíno → Fila de revisão resolve e reabre um item sem deixar
efeito colateral. Executado duas vezes seguidas para confirmar
repetibilidade; estado da fila de revisão confirmado inalterado
(163 pendentes) depois do teste.

## 6. Instruções para executar o programa

```bash
# uma vez (corpus real em data/raw/, fora do git — ver ADR 0002):
python3 scripts/ingest_vertical.py
python3 scripts/extract_concepts.py

# a cada uso:
./run.sh
```

Abrir `http://localhost:8000`. Requisitos: Python 3.11+, Node.js 18+.
`run.sh` instala dependências na primeira execução e builda a
interface automaticamente. Detalhes e comandos de teste em `README.md`.

## 7. Limitações realmente remanescentes

Sem eufemismo — o que está listado aqui não foi resolvido nesta
entrega:

- **Escopo de um único vertical.** Generalizar para os outros 209
  `exam_type` do corpus (outras articulações, TC, RX) é trabalho novo:
  cada vertical historicamente revelou padrões estruturais próprios
  (Fase 1) e vocabulário clínico próprio (Fase 4) que não se
  transferem automaticamente.
- **Cobertura de extração ~58%.** Quase metade das sentenças de
  achados/impressão não geram nenhum conceito estruturado — descrevem
  achados reais para os quais não existe regra ainda (cauda longa:
  perimeniscite, ectasia venosa, corpos livres, edema da gordura de
  Hoffa, alterações pós-cirúrgicas não cobertas pela fila de revisão,
  entre outros). Isso é uma lacuna de recall — informação omitida, não
  informação errada — mas significa que a Biblioteca de achados na UI
  não cobre tudo que os laudos reais descrevem.
- **Sem gold standard clínico.** A validação de fidelidade textual (86
  sentenças, ADR 0007) foi feita por leitura sistemática minha, não por
  um radiologista — mede se o conceito bate com o texto, não se é a
  forma clinicamente correta de descrever o achado. Nenhuma métrica de
  precisão clínica real existe ainda.
- **Reuso de frase real não é uma garantia de conteúdo exato.** O
  compilador nunca gera prosa, mas uma frase real reaproveitada pode
  conter informação além do achado pedido, se a extração não capturou
  tudo o que ela diz (ADR 0006). Todo laudo compilado precisa de
  revisão médica integral — isso é uma limitação estrutural da
  arquitetura de reuso, não um detalhe de acabamento.
- **Auditor determinístico é leve.** Cobre contradição de status e
  duplicidade exata no pedido, e impressão citando estrutura ausente
  dos achados — não cobre o conjunto completo de regras clínicas
  descrito na especificação original (lateralidade cruzada, medidas
  incompatíveis com o achado, etc.), que exigiriam mais tempo de
  curadoria por vertical.
- **163 itens na fila de revisão clínica** aguardando julgamento
  humano (89 de risco alto — contexto pós-cirúrgico/reconstrução —, 50
  médio, 24 baixo). Ver seção 8.
- **Sem LLM em nenhuma camada.** Deliberado nesta entrega (ver
  ESPECIFICACAO_MESTRA seção 20), mas significa que o sistema nunca
  reescreve, resume ou adapta uma frase — só escolhe entre as que já
  existem literalmente no corpus.
- **`run.sh` ainda não testado em outra máquina** além deste ambiente
  de desenvolvimento — os requisitos (Python 3.11+, Node 18+) foram
  verificados aqui, não em uma instalação limpa de terceiros.

## 8. Fila final consolidada de casos que exigem julgamento clínico

**163 itens pendentes**, acessíveis na tela "Fila de revisão clínica"
da interface (não reproduzidos aqui — contêm texto real de laudo, ver
ADR 0002):

| Motivo | Risco | Quantidade | Por quê não foi decidido automaticamente |
|---|---|---|---|
| Contexto pós-cirúrgico/reconstrução | Alto | 89 | Achado pode se referir à estrutura nativa ou ao material de enxerto/reconstrução — o extrator não distingue os dois casos, e decidir sem contexto adicional seria adivinhação. |
| Linguagem de incerteza no texto original | Médio/baixo | 49 | O próprio radiologista expressou incerteza diagnóstica (`sugestivo de`, `não se pode excluir`...) — o sistema torna essa incerteza visível, não a resolve. |
| Múltiplas medidas na mesma sentença | Baixo | 24 | Mais de uma medida em cm na frase — não é seguro assumir automaticamente qual corresponde ao achado extraído. |
| Cabeçalho de seção não reconhecido | Médio | 1 | Conteúdo que o parser da Fase 1 não conseguiu classificar em nenhuma seção conhecida. |

Cada item, na interface, mostra: trecho original completo, saída
estruturada que o sistema produziu (ou vazio, no caso de cabeçalho não
reconhecido), regra que disparou o sinalizador, motivo da dúvida, e
nível de risco — exatamente os 5 campos pedidos. A fila é persistente
(sobrevive a reprocessamento do pipeline, ADR 0008) e a decisão de
revisar fica registrada com nota opcional.

## 9. Resumo dos arquivos alterados e decisões técnicas

**9 commits**, **88 arquivos**, ~10.200 linhas adicionadas nesta
sessão. Por área:

- `backend/normalization/`, `backend/parsers/` (Fase 1) — normalização
  RAW/clean/normalized, parser de seções orientado por cabeçalhos reais
  por médico, parser de sentenças.
- `backend/clinical/` — extração de conceitos por regras
  (`knee_concepts.py`), fila de ambiguidade (`review_queue.py`),
  rótulos de exibição PT-BR (`labels.py`).
- `backend/compiler/` — banco de frases reais (`phrase_bank.py`,
  preferindo frases "limpas"), montagem do laudo (`report_compiler.py`).
- `backend/api/` — API FastAPI (5 routers, schemas Pydantic, conexão
  ao SQLite).
- `frontend/` — interface React completa (4 páginas, componentes de UI,
  cliente de API tipado).
- `scripts/` — pipeline de ingestão, extração, compilação de exemplo,
  teste de ponta a ponta.
- `tests/` — 133 testes automatizados.
- `docs/decisions/0001` a `0009` — uma decisão técnica registrada por
  ADR, incluindo as reversíveis e o porquê de cada uma (SQLite em vez
  de Postgres nesta fase, Vite em vez de Next.js, corpus fora do Git,
  fila com UPSERT preservando julgamento humano, entre outras).

Decisões técnicas centrais, cada uma com sua justificativa completa no
ADR correspondente:

- Vertical único antes de generalizar (`docs/architecture.md`).
- Corpus bruto e banco de dados nunca commitados no Git (ADR 0002).
- SQLite nesta fase, migração para Postgres é mecânica quando
  necessária (ADR 0004).
- Extração 100% por regras, sem LLM em nenhuma camada (ADR 0005).
- Fila de revisão com UPSERT por chave natural, preservando revisão
  humana entre reprocessamentos (ADR 0008).
- Vite + React sem biblioteca de componentes, servido pela própria API
  num único processo (ADR 0009).

## 10. Capturas de tela e demonstração do fluxo real

Enviadas diretamente na conversa (não commitadas no repositório —
mostram texto real de laudo e combinações doutor+exame+data que, em
conjunto, têm potencial de reidentificação; mesma régua de privacidade
da ADR 0002, aplicada a imagens). Cobrem: Dashboard com contagens
reais, Biblioteca com um laudo real e sua classificação lado a lado, o
fluxo completo de montagem de um laudo no Compilador (achado
selecionado → laudo compilado → rastreabilidade até a frase e o médico
de origem), e a Fila de Revisão Clínica com casos reais de contexto
pós-cirúrgico.

Geradas por `scripts/e2e_smoke_test.py`, o mesmo script que valida o
fluxo de ponta a ponta (seção 5) — não são capturas avulsas, são o
resultado do teste automatizado passando contra a aplicação real.
