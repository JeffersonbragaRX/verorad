"""Report Compiler — RM de joelho (Fase 6, vertical piloto).

Regra central do projeto (ESPECIFICACAO_MESTRA secao 20): o compilador
REDIGE, nao OBSERVA. So pode usar achados explicitamente fornecidos
pelo chamador (o medico) — nunca acrescenta, remove ou infere um
achado por conta propria. A funcao do compilador e escolher, para cada
achado JA DECIDIDO pelo medico, a frase REAL mais adequada no corpus
(via PhraseBank) — nunca gerar prosa livre (sem LLM nesta fase).

Se nao houver frase real para um achado solicitado, o achado fica em
'unresolved' — NAO e' preenchido com texto generico nem omitido em
silencio (contrato do relatorio: sinalizar lacuna, nunca inventar). O
mesmo vale para tecnica e impressao: se nao houver dado real para
preencher, a secao fica de fora e um aviso explica o motivo — nunca um
texto generico ('tecnica mais comum do corpus', 'sem alterações
significativas') e' inserido sem o chamador ter pedido isso
explicitamente (ver ADR 0010, auditoria externa que encontrou este e
outros bugs de fabricacao silenciosa nesta camada).
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from backend.compiler.phrase_bank import PhraseBank, build_phrase_bank

# Ordem de redacao convencional para RM de joelho (menisco -> ligamentos
# -> cartilagem/compartimentos -> derrame -> cistos -> tendoes -> patela).
# Usada so para ORDENAR achados ja fornecidos, nunca para decidir quais
# achados incluir.
_STRUCTURE_ORDER = [
    "meniscus_medial", "meniscus_lateral",
    "acl", "pcl", "mcl", "lcl",
    "knee_joint",
    "joint_space",
    "baker_cyst", "parameniscal_cyst", "ganglion_cyst",
    "bone",
    "quadriceps_tendon", "patellar_tendon", "tendon_unspecified",
    "patella", "retinaculum",
]

# Prefixos de aviso que representam risco real de conteudo clinico
# incorreto (nao apenas estilo) — bloqueiam copiar/exportar ate revisao
# manual. Outros avisos (DUPLICIDADE, MÉDICO, AUDITOR, IMPRESSÃO,
# TÉCNICA) sao informativos e nao impedem o uso, mas ficam visiveis.
_BLOCKING_WARNING_PREFIXES = ("CONTRADIÇÃO:", "LATERALIDADE:")


def _structure_sort_key(structure: str) -> int:
    try:
        return _STRUCTURE_ORDER.index(structure)
    except ValueError:
        return len(_STRUCTURE_ORDER)


@dataclass
class FindingRequest:
    """Um achado decidido pelo medico — a UNICA entrada de conteudo
    clinico aceita pelo compilador."""
    structure: str
    finding: str
    status: str = "present"  # 'present' | 'absent'
    severity: str | None = None
    location: str | None = None

    def key(self) -> tuple:
        return (self.structure, self.finding, self.status, self.severity, self.location)


@dataclass
class ResolvedFinding:
    request: FindingRequest
    text: str
    source_doctor: str
    matched_key: tuple
    exact_match: bool  # False se a busca relaxou severidade/localizacao


@dataclass
class CompileResult:
    technique_text: str | None
    findings_lines: list[ResolvedFinding] = field(default_factory=list)
    impression_lines: list[ResolvedFinding] = field(default_factory=list)
    unresolved: list[FindingRequest] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        """True quando ha' pelo menos um aviso que representa risco
        clinico real (contradicao, mistura de lateralidade) — o
        chamador (API/interface) deve impedir copiar/exportar ate o
        medico revisar e resolver manualmente."""
        return any(w.startswith(_BLOCKING_WARNING_PREFIXES) for w in self.warnings)

    def render(self, indication_text: str | None = None) -> str:
        parts = []
        if indication_text:
            parts.append(f"INDICAÇÃO CLÍNICA:\n{indication_text}")
        if self.technique_text:
            parts.append(f"TÉCNICA:\n{self.technique_text}")
        if self.findings_lines:
            parts.append("RELATÓRIO:\n" + "\n".join(f.text for f in self.findings_lines))
        if self.impression_lines:
            parts.append("IMPRESSÃO DIAGNÓSTICA:\n" + "\n".join(f.text for f in self.impression_lines))
        return "\n\n".join(parts)


def _validate_no_contradictions(findings: list[FindingRequest]) -> list[str]:
    warnings = []
    seen: dict[tuple, str] = {}
    seen_exact: dict[tuple, int] = {}
    for f in findings:
        base = (f.structure, f.finding)
        if base in seen and seen[base] != f.status:
            warnings.append(
                f"CONTRADIÇÃO: '{f.structure}/{f.finding}' solicitado como "
                f"'{seen[base]}' e também como '{f.status}' na mesma requisição."
            )
        seen[base] = f.status

        exact_key = f.key()
        seen_exact[exact_key] = seen_exact.get(exact_key, 0) + 1
        if seen_exact[exact_key] == 2:  # avisa uma unica vez, na segunda ocorrencia
            warnings.append(
                f"DUPLICIDADE: '{f.structure}/{f.finding}' ({f.status}"
                f"{', ' + f.severity if f.severity else ''}"
                f"{', ' + f.location if f.location else ''}) foi solicitado mais de uma vez."
            )
    return warnings


def suggest_technique_candidates(
    conn: sqlite3.Connection, doctor: str | None = None, limit: int = 5,
) -> list[dict]:
    """Sugestoes de texto de tecnica vindas de OUTROS exames reais do
    corpus, ordenadas por frequencia — nunca aplicadas automaticamente
    a um laudo (ver ADR 0010: preencher tecnica silenciosamente, sem o
    chamador ter fornecido nem confirmado nada sobre o exame atual, era
    um bug real desta camada). O chamador (interface) apresenta isto
    como sugestao explicita; so vira 'technique_text' do laudo se o
    medico selecionar uma delas."""
    rows = conn.execute(
        """
        SELECT r.doctor, rs.text_clean
        FROM report_sections rs
        JOIN reports r ON rs.report_id = r.id
        WHERE rs.section_type = 'technique'
        """
    ).fetchall()
    if not rows:
        return []
    counter = Counter(rows)
    if doctor:
        doctor_counter = Counter((d, t) for d, t in rows if d == doctor)
        if doctor_counter:
            counter = doctor_counter
    out = []
    for (doc, text), freq in counter.most_common(limit):
        out.append({"text": text, "doctor": doc, "frequency": freq})
    return out


def compile_report(
    conn: sqlite3.Connection,
    findings: list[FindingRequest],
    doctor: str | None = None,
    laterality: str | None = None,
    technique_text: str | None = None,
    phrase_bank: PhraseBank | None = None,
) -> CompileResult:
    if phrase_bank is None:
        phrase_bank = build_phrase_bank(conn)

    warnings = _validate_no_contradictions(findings)

    # duplicidade exata ja foi sinalizada acima — nao compila a mesma
    # linha duas vezes no laudo, so a primeira ocorrencia conta.
    seen_keys: set[tuple] = set()
    deduplicated = []
    for f in findings:
        if f.key() in seen_keys:
            continue
        seen_keys.add(f.key())
        deduplicated.append(f)

    ordered = sorted(deduplicated, key=lambda f: _structure_sort_key(f.structure))

    # TÉCNICA: nunca preenchida automaticamente a partir de outro
    # exame do corpus. So aparece se o chamador forneceu explicitamente
    # (o medico confirmou um texto real, proprio ou de uma sugestao —
    # ver suggest_technique_candidates). Bug real corrigido (ADR 0010):
    # esta funcao antes escolhia sozinha a tecnica mais frequente do
    # corpus, mesmo sem o chamador ter informado nada sobre o exame
    # atual — podia inserir campo magnético/protocolo nao autorizados.
    if not technique_text:
        warnings.append(
            "TÉCNICA: não informada — nenhum texto de técnica foi incluído "
            "automaticamente; preencha manualmente ou selecione uma sugestão."
        )

    result = CompileResult(technique_text=technique_text, warnings=warnings)

    for f in ordered:
        candidate, matched_key = phrase_bank.lookup_relaxed(
            f.structure, f.finding, f.status, f.severity, f.location,
            section_type="findings", preferred_doctor=doctor, preferred_laterality=laterality,
        )
        if candidate is None:
            result.unresolved.append(f)
            continue
        exact = matched_key == (f.structure, f.finding, f.status, f.severity, f.location, "findings")
        result.findings_lines.append(ResolvedFinding(
            request=f, text=candidate.text, source_doctor=candidate.doctor,
            matched_key=matched_key, exact_match=exact,
        ))
        _append_selection_warnings(result, f, candidate)

        # IMPRESSÃO: tentada para QUALQUER status (present OU absent) —
        # bug real corrigido (ADR 0010): so buscava frase de impressao
        # para achados 'present'; achados 'absent' nunca geravam linha
        # de impressao, o que levava ao fallback fabricado removido
        # abaixo. Uma frase real de impressao para um achado ausente
        # ('Menisco lateral sem sinais de lesão.') e' tao legitima
        # quanto uma para um achado presente.
        imp_candidate, imp_key = phrase_bank.lookup_relaxed(
            f.structure, f.finding, f.status, f.severity, f.location,
            section_type="impression", preferred_doctor=doctor, preferred_laterality=laterality,
        )
        if imp_candidate is not None:
            result.impression_lines.append(ResolvedFinding(
                request=f, text=imp_candidate.text, source_doctor=imp_candidate.doctor,
                matched_key=imp_key,
                exact_match=imp_key == (f.structure, f.finding, f.status, f.severity, f.location, "impression"),
            ))
            _append_selection_warnings(result, f, imp_candidate)
        # Sem frase real de impressao disponivel: NÃO reaproveita a de
        # achados nem insere texto generico. O achado fica so no corpo
        # de achados; a ausencia de impressao para ele fica visivel
        # (ver aviso IMPRESSÃO abaixo), nunca escondida atras de uma
        # frase que nao foi realmente dita para essa combinacao.

    # Bug real corrigido (ADR 0010, achado #1 da auditoria externa):
    # esta funcao inseria 'Exame sem alterações significativas.' sempre
    # que havia achados no corpo mas nenhuma linha de impressao real —
    # inclusive quando o unico achado fornecido era a AUSENCIA de UMA
    # estrutura especifica, transformando isso em normalidade GLOBAL do
    # exame inteiro (nunca autorizada pelo chamador). Removido: agora,
    # se faltou impressao real para algum achado, isso vira um aviso
    # explicito em vez de texto fabricado — a secao de impressao so
    # aparece com o que realmente foi encontrado no corpus.
    resolved_structures_with_impression = {rf.request.key() for rf in result.impression_lines}
    missing_impression = [
        f for f in ordered
        if f.key() not in resolved_structures_with_impression and f not in result.unresolved
    ]
    if missing_impression:
        missing_desc = ", ".join(f"{f.structure}/{f.finding}" for f in missing_impression)
        result.warnings.append(
            f"IMPRESSÃO: nenhuma frase real de impressão foi encontrada para "
            f"{missing_desc} — não incluída automaticamente; complete manualmente."
        )

    # NOTA (ADR 0010, achado #8 da auditoria externa): havia aqui uma
    # checagem de 'auditor' ("toda estrutura na impressao precisa estar
    # nos achados") coberta por um teste que nao exercitava a funcao
    # real — e ao investigar por que, descobrimos que a checagem em si
    # e' codigo morto: cada linha de impressao carrega o MESMO objeto
    # FindingRequest da linha de achados que a originou (ver 'request=f'
    # acima), entao 'estrutura da impressao ausente dos achados' e'
    # estruturalmente impossivel neste fluxo — nunca poderia disparar.
    # Removida em vez de mantida como protecao falsa; o invariante
    # (impression_lines so cita estruturas presentes em findings_lines)
    # e' garantido pela construcao acima e coberto por
    # test_impression_structures_are_always_subset_of_findings_structures.

    return result


def _append_selection_warnings(result: CompileResult, request: FindingRequest, candidate) -> None:
    """Bugs reais corrigidos (ADR 0010, achados #5 e #6 da auditoria
    externa): a escolha de frase podia reaproveitar, em silencio, uma
    frase de um exame do lado oposto que nomeia o lado explicitamente,
    ou uma frase de um medico diferente do solicitado — sem nenhum
    sinal disso no laudo final. Agora ambos os casos geram aviso
    visivel; lateralidade e' tratada como risco clinico (bloqueia
    copiar/exportar via CompileResult.blocking), medico e' informativo
    (estilo, nao correcao clinica)."""
    if candidate.mismatched_laterality:
        result.warnings.append(
            f"LATERALIDADE: frase de '{request.structure}/{request.finding}' foi "
            "reaproveitada de um exame do lado oposto e menciona o lado "
            "explicitamente — revise antes de usar."
        )
    if candidate.mismatched_doctor:
        result.warnings.append(
            f"MÉDICO: frase de '{request.structure}/{request.finding}' foi reaproveitada "
            f"de {candidate.doctor} — não havia frase real do médico preferido para esta combinação."
        )
