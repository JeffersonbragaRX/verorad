"""Report Compiler — RM de joelho (Fase 6, vertical piloto).

Regra central do projeto (ESPECIFICACAO_MESTRA secao 20): o compilador
REDIGE, nao OBSERVA. So pode usar achados explicitamente fornecidos
pelo chamador (o medico) — nunca acrescenta, remove ou infere um
achado por conta propria. A funcao do compilador e escolher, para cada
achado JA DECIDIDO pelo medico, a frase REAL mais adequada no corpus
(via PhraseBank) — nunca gerar prosa livre (sem LLM nesta fase).

Se nao houver frase real para um achado solicitado, o achado fica em
'unresolved' — NAO e' preenchido com texto generico nem omitido em
silencio (contrato do relatorio: sinalizar lacuna, nunca inventar).
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
        elif self.findings_lines:
            parts.append("IMPRESSÃO DIAGNÓSTICA:\nExame sem alterações significativas.")
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


def _pick_technique_text(conn: sqlite3.Connection, doctor: str | None) -> str | None:
    rows = conn.execute(
        """
        SELECT r.doctor, rs.text_clean
        FROM report_sections rs
        JOIN reports r ON rs.report_id = r.id
        WHERE rs.section_type = 'technique'
        """
    ).fetchall()
    if not rows:
        return None
    if doctor:
        doctor_rows = [text for doc, text in rows if doc == doctor]
        if doctor_rows:
            return Counter(doctor_rows).most_common(1)[0][0]
    return Counter(text for _doc, text in rows).most_common(1)[0][0]


def compile_report(
    conn: sqlite3.Connection,
    findings: list[FindingRequest],
    doctor: str | None = None,
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

    result = CompileResult(technique_text=_pick_technique_text(conn, doctor), warnings=warnings)

    for f in ordered:
        candidate, matched_key = phrase_bank.lookup_relaxed(
            f.structure, f.finding, f.status, f.severity, f.location,
            section_type="findings", preferred_doctor=doctor,
        )
        if candidate is None:
            result.unresolved.append(f)
            continue
        exact = matched_key == (f.structure, f.finding, f.status, f.severity, f.location, "findings")
        result.findings_lines.append(ResolvedFinding(
            request=f, text=candidate.text, source_doctor=candidate.doctor,
            matched_key=matched_key, exact_match=exact,
        ))

        if f.status == "present":
            imp_candidate, imp_key = phrase_bank.lookup_relaxed(
                f.structure, f.finding, f.status, f.severity, f.location,
                section_type="impression", preferred_doctor=doctor,
            )
            if imp_candidate is not None:
                result.impression_lines.append(ResolvedFinding(
                    request=f, text=imp_candidate.text, source_doctor=imp_candidate.doctor,
                    matched_key=imp_key,
                    exact_match=imp_key == (f.structure, f.finding, f.status, f.severity, f.location, "impression"),
                ))
            else:
                # sem frase de impressao real disponivel: reaproveita a de achados
                # em vez de inventar uma nova (ainda e uma frase real do corpus).
                result.impression_lines.append(ResolvedFinding(
                    request=f, text=candidate.text, source_doctor=candidate.doctor,
                    matched_key=matched_key, exact_match=False,
                ))

    # auditor leve: toda estrutura na impressao precisa estar nos achados
    findings_structures = {f.request.structure for f in result.findings_lines}
    for imp in result.impression_lines:
        if imp.request.structure not in findings_structures:
            result.warnings.append(
                f"AUDITOR: estrutura '{imp.request.structure}' aparece na impressão "
                "mas não no corpo de achados — bloquear revisão manual."
            )

    return result
