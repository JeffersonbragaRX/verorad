# ADR 0010 — Correções decorrentes de auditoria externa (extrator e compilador)

**Status:** aceito

## Contexto

Uma auditoria técnica externa (comparando esta implementação com uma
implementação paralela feita noutra ferramenta) comparou os dois
pacotes contra a especificação mestra e apontou 8 falhas concretas na
camada de extração de conceitos (Fase 4) e no Report Compiler (Fase 6)
desta implementação — algumas delas classificadas como bloqueantes
para uso clínico. Cada uma foi verificada diretamente no código-fonte
antes de qualquer correção (nenhuma foi aceita ou corrigida só por
constar no relatório da auditoria); todas as 8 se confirmaram reais.

Ao investigar as 8, mais uma classe de bug real foi encontrada por
conta própria (não fazia parte da auditoria) e corrigida na mesma
rodada: vários extratores de achado nunca verificavam negação — "não
há sinais de condropatia" e "sem edema subcondral" eram extraídos como
achado PRESENTE. A segunda foi confirmada contra o corpus real: 228
das 730 sentenças que mencionam "edema subcondral" o fazem negado.

## O que foi corrigido

### 1. Extrator de conceitos (`backend/clinical/knee_concepts.py`)

**Negação escopada por cláusula, não pela sentença inteira.** Antes,
`negated = _has_any(text, _NEGATION_CUES)` rodava sobre a sentença
inteira. Em frases coordenadas ("Rotura do ligamento cruzado anterior,
sem lesão meniscal." / "Menisco medial sem roturas, observando-se
lesão do menisco lateral.") isso fazia a negação de uma estrutura
"vazar" para outra mencionada na mesma sentença, apagando um achado
afirmado. Corrigido com `_segment_containing()`: escopa ao(s)
segmento(s) separados por vírgula/ponto-e-vírgula relevantes à
estrutura, estendendo para segmentos seguintes só até encontrar menção
de OUTRA estrutura conhecida (evita também quebrar qualificadores da
MESMA estrutura, como "verticalizado, porém íntegro."). Aplicado em
menisco (por lado), LCA/LCP e colaterais (também escopou a severidade,
que tinha o mesmo problema).

**Negação ausente em condropatia, edema ósseo, cistos, tendinopatia e
fratura por insuficiência.** Nenhum desses extratores checava negação
— qualquer menção da palavra-chave virava "presente". Corrigido com
`_negated_near()`, que cobre tanto os cues compostos já curados
(`_NEGATION_CUES`) quanto o padrão dominante nestes achados específicos
("sem <achado>", "sem focos de <achado>" — sem frase composta
pré-cadastrada). Condropatia e edema ósseo tinham casos reais
confirmados no corpus; cisto/tendinopatia/fratura por insuficiência
não tinham nenhum caso observado no corpus atual, mas receberam a
mesma proteção por serem a mesma classe de bug.

### 2. Report Compiler (`backend/compiler/report_compiler.py`, `phrase_bank.py`)

**Normalidade global inventada removida.** `render()` inseria "Exame
sem alterações significativas." sempre que havia achados no corpo mas
nenhuma linha de impressão real — inclusive quando o único achado
pedido era a ausência de UMA estrutura específica, transformando isso
em normalidade do exame INTEIRO (nunca autorizado pelo chamador; a
especificação proíbe expressamente isso). Um teste antigo chegava a
afirmar esse comportamento como correto. Removido: a seção de
impressão só aparece com frases reais encontradas; a ausência gera um
aviso `IMPRESSÃO:` explícito em vez de texto fabricado. Como parte
disso, a busca de frase de impressão passou a rodar para achados
`present` E `absent` (antes só tentava para `present`, o que também
contribuía para a lacuna).

**Técnica não é mais copiada de outro exame em silêncio.**
`_pick_technique_text()` escolhia a técnica mais frequente do CORPUS
inteiro, sem receber nenhum dado do exame atual — podia inserir campo
magnético, sequências ou protocolo de outro paciente sem autorização.
Removido do fluxo automático: `compile_report()` só preenche
`technique_text` se o chamador fornecer explicitamente. A busca por
frequência agora é `suggest_technique_candidates()`, exposta como
sugestão via `GET /api/technique-suggestions` — o médico escolhe (ou
escreve a própria) e o texto só entra no laudo se for enviado de volta
explicitamente em `POST /api/compile`.

**Lateralidade agora participa da escolha de frase.** Nem
`FindingRequest`/`CompileRequestIn` nem a chave do `PhraseBank`
carregavam lado do exame — uma frase de um exame D podia ser
reaproveitada para um laudo E mesmo nomeando o lado explicitamente no
texto. `compile_report()` e `PhraseBank.lookup()` ganharam parâmetro
`laterality`; cada frase do banco carrega o lado do exame de origem
(derivado de `exam_type`, sem precisar de novo JOIN). Uma frase de
lado oposto que **nomeia o lado no próprio texto** ("joelho direito")
só é usada como último recurso e gera aviso `LATERALIDADE:` —
classificado como bloqueante (ver abaixo). Frases sem menção de lado
(a maioria — "menisco lateral" é compartimento anatômico, não
lateralidade do joelho) não disparam o aviso.

**Mistura de médico agora é visível.** `PhraseBank.lookup()` já caía
para o médico mais frequente geral quando o preferido não tinha frase
para aquela chave — sem sinalizar. Agora gera aviso `MÉDICO:`
(informativo, não bloqueante — é uma questão de estilo/consistência de
redação, não de conteúdo clínico incorreto).

**Contradições agora bloqueiam copiar/exportar.** `CompileResult`
ganhou a propriedade `blocking`, calculada a partir de prefixos de
aviso que representam risco clínico real (`CONTRADIÇÃO:`,
`LATERALIDADE:`). Exposta como `blocking: bool` em
`CompileResponseOut`. No frontend (`Compiler.tsx`), os botões Copiar e
Exportar ficam desabilitados enquanto `blocking=true`, com mensagem
explicando o motivo. Avisos informativos (`DUPLICIDADE:`, `MÉDICO:`,
`TÉCNICA:`, `IMPRESSÃO:`) continuam visíveis mas não bloqueiam.

**Teste do "auditor" — removido, não só corrigido.** O teste
`test_auditor_flags_impression_structure_absent_from_findings` rodava
`compile_report` com achados vazios, depois injetava manualmente um
`ResolvedFinding` falso em `impression_lines` e reimplementava a
asserção na mão em vez de exercitar a lógica real. Ao investigar por
que o teste precisava desse contorno, descobriu-se que a checagem que
ele fingia cobrir era código morto de verdade: cada linha de impressão
carrega o MESMO objeto `FindingRequest` da linha de achados que a
originou (`request=f`), então "estrutura da impressão ausente dos
achados" é estruturalmente impossível no fluxo atual — nunca poderia
disparar em produção. A checagem foi removida (mantê-la seria uma
proteção falsa) e substituída por um teste de invariante real
(`test_impression_structures_are_always_subset_of_findings_structures`),
que roda a função de verdade e verifica a garantia estrutural com
dados reais.

## Consequência

- Extração: 46 testes de regressão no extrator (39 → 46), cobrindo
  cada um dos casos acima com a frase real ou equivalente.
- Compilador: 25 testes (13 → 25), incluindo os novos cenários de
  lateralidade, mistura de médico e bloqueio.
- API: 26 testes (20 → 26), incluindo o novo endpoint de sugestão de
  técnica e o campo `blocking`.
- Suíte completa: 158 testes, todos passando.
- Corpus reprocessado do zero com as regras corrigidas: cobertura
  58,0% (10.777/18.597 sentenças), 15.221 conceitos (vs. 15.275
  antes — a redução líquida vem de sentenças de condropatia negadas
  que antes geravam múltiplos conceitos "presentes" por compartimento
  e agora geram um único conceito "ausente" corretamente), 161 itens
  na fila de revisão clínica (vs. 163 antes).
- `e2e_smoke_test.py` revalidado de ponta a ponta contra o corpus
  reprocessado e a interface com os novos campos (lado do exame,
  técnica).

## O que isto NÃO resolve

Esta rodada corrigiu bugs determinísticos de parsing/geração
encontrados por auditoria e por revisão própria subsequente — não é
uma validação clínica. Continuam válidas as limitações já documentadas
(ADR 0006, ADR 0007, README): recall ~58% (uma frase reaproveitada
pode conter mais do que o conceito extraído capturou), sem gold
standard clínico anotado por radiologista, escopo limitado a RM de
joelho. A heurística de segmentação por vírgula em
`_segment_containing()` é pontuação, não um parser sintático — cobre
os casos reais observados no corpus, mas coordenações sem vírgula
continuam sendo uma limitação conhecida.
