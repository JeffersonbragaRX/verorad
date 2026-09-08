"""Clinical Concept Layer universal — Fase 4B.

Monta conceitos clinicos estruturados a partir de duas camadas ja
existentes, sem regra por tipo de exame:

  clause_engine  -> escopo (negacao, certeza, temporalidade, medida...)
  lexicon        -> o que e' anatomia, achado, atributo, descritor

Regra de montagem: dentro de uma CLAUSULA, cada mencao de ACHADO
recebe (a) o status/certeza/temporalidade resolvidos POR POSICAO pelo
clause engine e (b) a estrutura anatomica mais proxima na mesma
clausula. Uma clausula que so tem anatomia + normalidade explicita
gera um conceito de normalidade daquela estrutura — que e' diferente
de 'nao mencionado' (que nao gera nada, nunca).

O schema segue a secao 7 do PROMPT MESTRE V2: nucleo universal, com
campos opcionais por dominio. Campo ausente fica None — nunca e'
preenchido por prevalencia, template ou habito do medico.

Proveniencia obrigatoria em todo conceito: report/section/sentence,
span de caracteres da mencao, regra que o gerou, versao do extrator e
confianca. Sem isso nao ha' auditoria possivel.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, asdict

from backend.clinical.clause_engine import (
    ClauseAnalysis, analyze_sentence, strip_accents, ENGINE_VERSION,
)
from backend.clinical.lexicon import LEXICON_VERSION

CONCEPT_LAYER_VERSION = "concept_layer/1.0.0"


@dataclass
class ClinicalConcept:
    """Schema universal (secao 7 do prompt mestre). Campos nao
    aplicaveis ao dominio permanecem None."""
    # identificacao
    modality: str
    domain: str
    exam_type: str
    doctor: str
    section_type: str
    # nucleo clinico
    structure: str | None
    finding: str | None
    status: str                     # present | absent | normal | not_assessed
    certainty: str                  # definite | probable | possible | cannot_exclude
    # atributos
    severity: str | None = None
    morphology: str | None = None
    distribution: str | None = None
    grade: str | None = None
    laterality: str | None = None
    laterality_source: str | None = None   # exam_metadata | sentence_local | conflict
    measurements: list[float] = field(default_factory=list)
    measurement_unit: str | None = None
    temporal_status: str | None = None
    comparison_status: str | None = None
    etiologic_qualifier: str | None = None
    postoperative_context: str | None = None
    modifiers: list[str] = field(default_factory=list)
    # proveniencia
    report_id: int = 0
    section_id: int = 0
    sentence_id: int = 0
    char_start: int = 0
    char_end: int = 0
    source_span: str = ""
    extraction_method: str = ""
    rule_id: str = ""
    engine_version: str = ENGINE_VERSION
    lexicon_version: str = LEXICON_VERSION
    layer_version: str = CONCEPT_LAYER_VERSION
    confidence: float = 0.0
    validation_status: str = "extraction_candidate"


class ConceptExtractor:
    """Extrator universal. Recebe o lexico ja minerado (dict termo ->
    (tipo, confianca)) e opera igual em qualquer dominio."""

    def __init__(self, lexicon: dict[str, tuple[str, float]]):
        self.lexicon = lexicon
        # indexa por numero de palavras para casar o termo mais longo
        self.max_len = max((len(t.split()) for t in lexicon), default=1)

    def _find_mentions(self, norm_text: str) -> list[tuple[str, str, float, int, int]]:
        """Casa termos do lexico no texto normalizado, preferindo o
        termo MAIS LONGO em cada posicao ('abaulamento discal' vence
        'abaulamento'). Retorna (termo, tipo, confianca, start, end)."""
        import re
        tokens = [(m.group(), m.start(), m.end())
                  for m in re.finditer(r"[a-zà-ÿ]+", norm_text)]
        mentions = []
        i = 0
        while i < len(tokens):
            matched = False
            for n in range(min(self.max_len, len(tokens) - i), 0, -1):
                gram = " ".join(t[0] for t in tokens[i:i + n])
                hit = self.lexicon.get(gram)
                if hit:
                    term_type, conf = hit
                    mentions.append((gram, term_type, conf,
                                      tokens[i][1], tokens[i + n - 1][2]))
                    i += n
                    matched = True
                    break
            if not matched:
                i += 1
        return mentions

    def extract(self, sentence_text: str, *, report_id: int, section_id: int,
                sentence_id: int, modality: str, domain: str, exam_type: str,
                doctor: str, section_type: str,
                exam_laterality: str | None = None) -> list[ClinicalConcept]:
        analysis = analyze_sentence(sentence_text)
        norm = analysis.sentence_normalized
        mentions = self._find_mentions(norm)
        if not mentions:
            return []

        findings = [m for m in mentions if m[1] == "finding"]
        anatomies = [m for m in mentions if m[1] == "anatomy"]
        modifiers = [m for m in mentions if m[1] in ("modifier", "descriptor")]
        by_axis = {
            axis: [m for m in mentions if m[1] == axis]
            for axis in ("severity", "morphology", "distribution")
        }

        concepts: list[ClinicalConcept] = []

        def nearest_anatomy(start: int, end: int) -> tuple[str | None, float]:
            """Estrutura mais proxima NA MESMA CLAUSULA. Prefere a que
            vem antes (ordem tipica: '<achado> do <estrutura>' tem a
            estrutura depois; '<estrutura> com <achado>' tem antes —
            entao a proximidade e' o criterio, nao a ordem)."""
            clause = analysis.clause_at(start)
            if clause is None:
                return None, 0.0
            best, best_dist = None, 10 ** 9
            for term, _t, conf, a_start, a_end in anatomies:
                if not (clause.char_start <= a_start <= clause.char_end):
                    continue
                dist = min(abs(a_start - end), abs(start - a_end))
                if dist < best_dist:
                    best, best_dist = (term, conf), dist
            if best is None:
                return None, 0.0
            return best[0], best[1]

        def axis_in_clause(axis: str, start: int) -> str | None:
            """Atributo do eixo pedido, dentro da MESMA clausula. Cada
            eixo (severidade, morfologia, distribuicao) vai para o seu
            proprio campo — colapsa-los num so punha 'bilateral' e
            'parcial' no campo de gravidade."""
            clause = analysis.clause_at(start)
            if clause is None:
                return None
            hits = [t for t, _ty, _c, s, _e in by_axis[axis]
                    if clause.char_start <= s <= clause.char_end]
            return hits[0] if hits else None

        def mods_in_clause(start: int) -> list[str]:
            clause = analysis.clause_at(start)
            if clause is None:
                return []
            return [t for t, _ty, _c, s, _e in modifiers
                    if clause.char_start <= s <= clause.char_end]

        def resolve_laterality(start: int, end: int) -> tuple[str | None, str | None]:
            """Lateralidade LOCAL vence a global do exame, mas o
            conflito e' registrado — 'direita no cabecalho, esquerda no
            corpo' e' um caso adversarial exigido pelo prompt e nao
            pode ser resolvido em silencio."""
            local = analysis.laterality_at(start, end)
            glob = {"D": "right", "E": "left"}.get(exam_laterality or "", None)
            if local and glob and local != glob and local != "bilateral":
                return local, "conflict"
            if local:
                return local, "sentence_local"
            if glob:
                return glob, "exam_metadata"
            return None, None

        def build(structure, finding, start, end, rule_id, base_conf) -> ClinicalConcept:
            status, _cue = analysis.status_at(start, end)
            lat, lat_src = resolve_laterality(start, end)
            meas = analysis.measurements_for(start, end)
            grades = analysis.grades_for(start, end)
            return ClinicalConcept(
                modality=modality, domain=domain, exam_type=exam_type, doctor=doctor,
                section_type=section_type,
                structure=structure, finding=finding,
                status=status,
                certainty=analysis.certainty_at(start, end),
                severity=axis_in_clause("severity", start),
                morphology=axis_in_clause("morphology", start),
                distribution=axis_in_clause("distribution", start),
                grade=grades[0] if grades else None,
                laterality=lat, laterality_source=lat_src,
                measurements=meas[0].values if meas else [],
                measurement_unit=meas[0].unit if meas else None,
                temporal_status=analysis.temporality_at(start, end),
                comparison_status=analysis.comparison_at(start, end),
                etiologic_qualifier=analysis.etiologic_at(start, end),
                postoperative_context=analysis.postop_at(start, end),
                modifiers=mods_in_clause(start),
                report_id=report_id, section_id=section_id, sentence_id=sentence_id,
                char_start=start, char_end=end,
                source_span=sentence_text[start:end],
                extraction_method="clause_engine+lexicon",
                rule_id=rule_id, confidence=base_conf,
            )

        # 1) Um conceito por mencao de ACHADO.
        claimed_clauses = set()
        for term, _t, conf, start, end in findings:
            structure, s_conf = nearest_anatomy(start, end)
            concepts.append(build(structure, term, start, end,
                                   "finding_mention", round(min(conf, s_conf or conf), 3)))
            clause = analysis.clause_at(start)
            if clause:
                claimed_clauses.add(clause.order)

        # 2) Normalidade explicita: clausula com anatomia + cue de
        #    normalidade e SEM achado. 'Meniscos preservados' afirma algo
        #    — e' diferente de nao mencionar o menisco (que nao gera nada).
        for term, _t, conf, start, end in anatomies:
            clause = analysis.clause_at(start)
            if clause is None or clause.order in claimed_clauses:
                continue
            status, cue = analysis.status_at(start, end)
            if status != "normal":
                continue
            concepts.append(build(term, None, start, end, "explicit_normality", conf))
            claimed_clauses.add(clause.order)

        return concepts


def load_lexicon_from_db(conn: sqlite3.Connection,
                          min_confidence: float = 0.5) -> dict[str, tuple[str, float]]:
    """Carrega o lexico persistido, so com os tipos que participam da
    montagem de conceito. 'unclassified' fica de fora por construcao —
    ele e' a cauda nao modelada, nao um tipo utilizavel."""
    usable = ("anatomy", "finding", "severity", "morphology", "distribution",
               "descriptor", "modifier")
    rows = conn.execute(
        f"""SELECT term, term_type, confidence FROM clinical_lexicon
            WHERE term_type IN ({','.join('?' * len(usable))})
              AND confidence >= ?""",
        (*usable, min_confidence),
    ).fetchall()
    return {term: (term_type, conf) for term, term_type, conf in rows}
