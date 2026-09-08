"""Clinical Concept Layer — RM de joelho (Fase 4, vertical piloto).

Extracao 100% baseada em regras (regex/keywords), sem LLM — em linha
com a regra central do projeto: nenhuma camada de IA generativa decide
sozinha o que e verdade clinica (ESPECIFICACAO_MESTRA secao 20). O
vocabulario de estruturas foi levantado por frequencia real nas 18.597
sentencas de achados/impressao do vertical (ver
docs/data_dictionary.md, secao "Vocabulario clinico do joelho").

Isto e um extrator v0: cobre os padroes de maior volume observados.
NAO ha ainda um conjunto de avaliacao anotado manualmente (gold
standard) — a cobertura reportada (% de sentencas com >=1 conceito) e
uma medida de RECALL aproximado, nao de precisao. Precisao real requer
revisao humana amostral (ver QA_REPORT_FASE4.json, secao
'manual_review_sample').

Cada conceito carrega 'rule_id' para rastreabilidade: qual regra o
gerou, sempre auditavel de volta ao texto original.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ORGAN = "knee"

# ---- cues compartilhados ---------------------------------------------

_NEGATION_CUES = [
    "sem sinais de", "sem evidências de", "sem evidencia de", "sem roturas",
    "sem rotura", "sem lesões", "sem lesão", "sem alterações significativas",
    "sem alterações", "sem alteração", "não há", "não apresenta",
    "ausência de", "nenhum sinal de",
]
_NORMAL_STATUS_WORDS = ["preservad", "íntegr", "normal", "usual", "habitual", "normopos"]
_HEDGE_CUES = [
    "sugestivo de", "pode representar", "podendo representar",
    "não se pode excluir", "possivelmente", "provavelmente",
    "podendo corresponder",
]
# stem (casa qualquer flexao de genero: -o/-a) -> forma canonica p/ armazenar
_SEVERITY_ADJECTIVES = {
    "acentuad": "acentuado", "importante": "importante", "volumos": "volumoso",
    "moderad": "moderado", "discret": "discreto", "leve": "leve",
    "pequen": "pequeno", "mínim": "mínimo", "incipiente": "incipiente",
}
_MEASUREMENT_RE = re.compile(r"(\d+(?:[,.]\d+)?)\s*cm\b")
_GRADE_RE = re.compile(r"grau\s*(i{1,3}v?|iv|[1-4])\b")

_ROMAN_TO_ARABIC = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}


def _has_any(text: str, needles: list[str]) -> bool:
    return any(n in text for n in needles)


def _has_word(text: str, word: str) -> bool:
    """Match com fronteira de palavra — necessario para termos curtos
    que sao prefixo de outra palavra (ex.: 'patela' e prefixo de
    'patelar'; um match por substring simples confundiria uma frase
    sobre o TENDAO patelar com um achado sobre o OSSO patela)."""
    return re.search(r"\b" + re.escape(word) + r"\b", text) is not None


def _first_severity(text: str) -> str | None:
    for stem, canonical in _SEVERITY_ADJECTIVES.items():
        if stem in text:
            return canonical
    return None


def _measurement_cm(text: str) -> float | None:
    m = _MEASUREMENT_RE.search(text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _grade(text: str) -> str | None:
    m = _GRADE_RE.search(text)
    if not m:
        return None
    g = m.group(1)
    return _ROMAN_TO_ARABIC.get(g, g)


def _certainty(text: str) -> str:
    return "equivocal" if _has_any(text, _HEDGE_CUES) else "definitive"


@dataclass
class ClinicalConcept:
    organ: str
    structure: str
    finding: str
    status: str  # present | absent | equivocal-not-used-here (equivocal e' em 'certainty')
    certainty: str
    rule_id: str
    severity: str | None = None
    location: str | None = None
    measurement_cm: float | None = None


@dataclass
class ConceptExtractionResult:
    concepts: list[ClinicalConcept] = field(default_factory=list)


# ---- extratores por estrutura ------------------------------------------

def _extract_meniscus(text: str) -> list[ClinicalConcept]:
    out = []
    sides = []
    if "menisco medial" in text:
        sides.append("meniscus_medial")
    if "menisco lateral" in text:
        sides.append("meniscus_lateral")
    if not sides and "meniscos" in text:
        sides = ["meniscus_medial", "meniscus_lateral"]
    if not sides:
        return out

    tear_kw = ["rotura", "lesão", "lesao", "fissura", "ruptura", "amputação"]
    degeneration_kw = ["degeneração", "degeneracao", "degenerativ"]
    has_tear_kw = _has_any(text, tear_kw)
    has_degeneration_kw = _has_any(text, degeneration_kw)
    negated = _has_any(text, _NEGATION_CUES)
    explicit_normal = _has_any(text, _NORMAL_STATUS_WORDS) or "sem evidências de lesões" in text

    location = None
    if "corno posterior" in text:
        location = "posterior_horn"
    elif "corno anterior" in text:
        location = "anterior_horn"
    elif "corpo do menisco" in text or "corpo meniscal" in text:
        location = "body"

    # tear e degeneracao sao EIXOS INDEPENDENTES — uma estrutura pode
    # estar degenerada e, ao mesmo tempo, sem rotura (achado real e
    # frequente: 'Degeneração difusa do menisco lateral, sem roturas.').
    # Tratar como if/elif (como numa versao anterior) fazia essa frase
    # composta parecer uma frase 'limpa' de 1 conceito so, o que
    # confundia o banco de frases do Report Compiler (Fase 6) na hora
    # de escolher frases reutilizaveis sem conteudo extra nao pedido.
    degeneration_negated = _has_any(text, [
        "sem degeneração", "sem sinais de degeneração", "sem alterações degenerativas",
    ])

    for structure in sides:
        if has_tear_kw and negated:
            out.append(ClinicalConcept(ORGAN, structure, "tear", "absent",
                                        _certainty(text), "meniscus_tear_negated",
                                        location=location))
        elif has_tear_kw and not negated:
            out.append(ClinicalConcept(ORGAN, structure, "tear", "present",
                                        _certainty(text), "meniscus_tear",
                                        location=location))
        elif explicit_normal:
            out.append(ClinicalConcept(ORGAN, structure, "tear", "absent",
                                        _certainty(text), "meniscus_explicit_normal",
                                        location=location))

        if has_degeneration_kw and not degeneration_negated:
            out.append(ClinicalConcept(ORGAN, structure, "degeneration", "present",
                                        _certainty(text), "meniscus_degeneration",
                                        severity=_first_severity(text), location=location))
    return out


def _extract_cruciate_ligaments(text: str) -> list[ClinicalConcept]:
    out = []
    for phrase, structure in [
        ("ligamento cruzado anterior", "acl"),
        ("ligamento cruzado posterior", "pcl"),
    ]:
        if phrase not in text:
            continue
        rupture_kw = ["rotura", "lesão", "lesao", "ruptura"]
        degeneration_kw = ["degeneração", "degeneracao", "degenerativ", "verticalizad"]
        negated = _has_any(text, _NEGATION_CUES)
        has_rupture = _has_any(text, rupture_kw)
        has_degeneration = _has_any(text, degeneration_kw)
        explicit_normal = _has_any(text, _NORMAL_STATUS_WORDS)

        severity = "complete" if "completa" in text else ("partial" if "parcial" in text else None)

        # tear e degeneracao sao eixos independentes (mesmo raciocinio
        # do menisco: 'verticalizado, com degeneração difusa, sem
        # roturas' descreve os dois ao mesmo tempo).
        if has_rupture and negated:
            out.append(ClinicalConcept(ORGAN, structure, "tear", "absent",
                                        _certainty(text), f"{structure}_tear_negated"))
        elif has_rupture and not negated:
            out.append(ClinicalConcept(ORGAN, structure, "tear", "present",
                                        _certainty(text), f"{structure}_tear",
                                        severity=severity))
        elif explicit_normal:
            out.append(ClinicalConcept(ORGAN, structure, "tear", "absent",
                                        _certainty(text), f"{structure}_explicit_normal"))

        if has_degeneration:
            out.append(ClinicalConcept(ORGAN, structure, "degeneration", "present",
                                        _certainty(text), f"{structure}_degeneration"))
    return out


def _extract_collateral_ligaments(text: str) -> list[ClinicalConcept]:
    out = []
    for phrase, structure in [
        ("ligamento colateral medial", "mcl"),
        ("ligamento colateral lateral", "lcl"),
    ]:
        if phrase not in text:
            continue
        injury_kw = ["rotura", "lesão", "lesao", "espessamento", "degeneração intersticial",
                     "degeneracao intersticial"]
        negated = _has_any(text, _NEGATION_CUES)
        explicit_normal = _has_any(text, _NORMAL_STATUS_WORDS)
        has_injury = _has_any(text, injury_kw)

        if has_injury and not negated:
            out.append(ClinicalConcept(ORGAN, structure, "injury", "present",
                                        _certainty(text), f"{structure}_injury"))
        elif has_injury and negated:
            out.append(ClinicalConcept(ORGAN, structure, "injury", "absent",
                                        _certainty(text), f"{structure}_injury_negated"))
        elif explicit_normal:
            out.append(ClinicalConcept(ORGAN, structure, "injury", "absent",
                                        _certainty(text), f"{structure}_explicit_normal"))
    return out


# Forma coordenada muito frequente ('ligamentos cruzados e colaterais
# íntegros/sem alterações'), que resume os 4 ligamentos numa unica
# mencao — sem isso, a sentenca nao bate com nenhuma das 4 frases
# completas usadas pelos extratores individuais acima e fica sem
# nenhum conceito extraido, mesmo descrevendo explicitamente que os
# 4 ligamentos estao normais.
def _extract_combined_ligaments_normal(text: str) -> list[ClinicalConcept]:
    if "ligamentos cruzados e colaterais" not in text:
        return []
    if not _has_any(text, _NORMAL_STATUS_WORDS + _NEGATION_CUES):
        return []
    finding_by_structure = {"acl": "tear", "pcl": "tear", "mcl": "injury", "lcl": "injury"}
    return [
        ClinicalConcept(ORGAN, structure, finding, "absent",
                         _certainty(text), f"{structure}_combined_explicit_normal")
        for structure, finding in finding_by_structure.items()
    ]


_COMPARTMENTS = [
    ("tricompartimental", "tricompartmental"),
    ("femoropatelar", "patellofemoral"),
    ("patelofemoral", "patellofemoral"),
    ("trócleopatelar", "patellofemoral"),
    ("tróclea patelar", "patellofemoral"),
    ("femorotibial medial", "medial_femorotibial"),
    ("femorotibial lateral", "lateral_femorotibial"),
    ("tibiofibular", "tibiofibular"),
    ("femorotibial", "femorotibial_unspecified"),
]


#  Fallback usado SOMENTE dentro do extrator de condropatia (contexto
#  ja restrito a uma frase que contem 'condropatia'/'artropatia
#  degenerativa'): 'condropatia patelar'/'condropatia troclear' sao
#  formas comuns de dizer patelofemoral sem usar essa palavra. Nao e
#  seguro promover isso para _COMPARTMENTS geral porque 'patelar'
#  sozinho tambem aparece em contextos de tendao, sem relacao com
#  compartimento articular.
_CHONDROPATHY_LOCAL_COMPARTMENT_FALLBACK = [
    ("patelar", "patellofemoral"),
    ("troclear", "patellofemoral"),
]


def _extract_chondropathy(text: str) -> list[ClinicalConcept]:
    out = []
    if "condropatia" not in text and "artropatia degenerativa" not in text:
        return out
    finding = "chondropathy" if "condropatia" in text else "degenerative_arthropathy"
    grade = _grade(text)
    severity = _first_severity(text)
    matched_any = False
    for phrase, location in _COMPARTMENTS:
        if phrase in text:
            matched_any = True
            out.append(ClinicalConcept(ORGAN, "knee_joint", finding, "present",
                                        _certainty(text), f"{finding}_{location}",
                                        severity=severity, location=location, ))
    if not matched_any:
        for phrase, location in _CHONDROPATHY_LOCAL_COMPARTMENT_FALLBACK:
            if phrase in text:
                matched_any = True
                out.append(ClinicalConcept(ORGAN, "knee_joint", finding, "present",
                                            _certainty(text), f"{finding}_{location}_fallback",
                                            severity=severity, location=location))
                break
    if not matched_any:
        out.append(ClinicalConcept(ORGAN, "knee_joint", finding, "present",
                                    _certainty(text), f"{finding}_unspecified_compartment",
                                    severity=severity))
    if grade:
        for c in out:
            c.severity = f"{c.severity}|grade_{grade}" if c.severity else f"grade_{grade}"
    return out


def _extract_effusion(text: str) -> list[ClinicalConcept]:
    out = []
    if not _has_any(text, ["derrame articular", "acúmulo líquido intra-articular",
                            "acumulo liquido intra-articular", "líquido articular"]):
        return out
    negated = _has_any(text, ["não há derrame", "sem derrame"])
    status = "absent" if negated else "present"
    out.append(ClinicalConcept(ORGAN, "joint_space", "effusion", status,
                                _certainty(text), "effusion",
                                severity=_first_severity(text)))
    return out


def _extract_cysts(text: str) -> list[ClinicalConcept]:
    out = []
    for phrase, structure in [
        ("cisto poplíteo", "baker_cyst"),
        ("cisto de baker", "baker_cyst"),
        ("cisto parameniscal", "parameniscal_cyst"),
        ("cisto gangliônico", "ganglion_cyst"),
        ("cisto gangliônico", "ganglion_cyst"),
    ]:
        if phrase in text:
            out.append(ClinicalConcept(ORGAN, structure, "cyst", "present",
                                        _certainty(text), "cyst",
                                        measurement_cm=_measurement_cm(text)))
    return out


def _extract_bone_marrow_edema(text: str) -> list[ClinicalConcept]:
    out = []
    if not _has_any(text, ["edema ósseo", "edema osseo", "edema medular",
                            "edema subcondral"]):
        return out
    location = None
    for phrase, loc in _COMPARTMENTS:
        if phrase in text:
            location = loc
            break
    out.append(ClinicalConcept(ORGAN, "bone", "bone_marrow_edema", "present",
                                _certainty(text), "bone_marrow_edema", location=location))
    return out


def _extract_tendinopathy(text: str) -> list[ClinicalConcept]:
    out = []
    if "tendinopatia" not in text:
        return out
    if "quadríceps" in text or "quadriceps" in text or "quadricipital" in text:
        structure = "quadriceps_tendon"
    elif "patelar" in text:
        structure = "patellar_tendon"
    else:
        structure = "tendon_unspecified"
    out.append(ClinicalConcept(ORGAN, structure, "tendinopathy", "present",
                                _certainty(text), "tendinopathy"))
    return out



# ("word", termo) usa fronteira de palavra — obrigatorio para 'patela',
# que e prefixo textual de 'patelar' (tendao patelar, retinaculo
# patelar, condropatia patelofemoral...). Um match por substring
# simples atribuiria erroneamente ao OSSO patela um achado que e do
# TENDAO patelar. Frases de 2+ palavras usam substring normal (seguro).
_GENERIC_NORMAL_STRUCTURES = [
    ("phrase", "tendão quadríceps", "quadriceps_tendon"),
    ("phrase", "tendão do quadríceps", "quadriceps_tendon"),
    ("phrase", "tendão patelar", "patellar_tendon"),
    ("word", "patela", "patella"),
    ("phrase", "complexo retinacular", "retinaculum"),
    ("phrase", "retináculo patelar", "retinaculum"),
]

# Construcoes coordenadas ('tendoes do quadriceps e patelar') que se
# referem a DOIS tendoes em uma unica mencao elidida — sem isso, o
# match generico so acharia o primeiro (ou nenhum, se 'patelar' sozinho
# nao bate com a frase completa 'tendao patelar').
_COORDINATED_TENDON_PATTERNS = [
    "tendões do quadríceps e patelar",
    "tendão quadríceps e patelar",
    "tendões quadríceps e patelar",
    "tendão do quadríceps e patelar",
]


def _extract_generic_normal(text: str, already_covered: set[str]) -> list[ClinicalConcept]:
    out = []
    if not _has_any(text, _NORMAL_STATUS_WORDS):
        return out

    if _has_any(text, _COORDINATED_TENDON_PATTERNS):
        for structure in ("quadriceps_tendon", "patellar_tendon"):
            if structure not in already_covered:
                out.append(ClinicalConcept(ORGAN, structure, "abnormality", "absent",
                                            _certainty(text), "generic_explicit_normal_coordinated"))
        already_covered = already_covered | {"quadriceps_tendon", "patellar_tendon"}

    for kind, needle, structure in _GENERIC_NORMAL_STRUCTURES:
        if structure in already_covered:
            continue
        matched = _has_word(text, needle) if kind == "word" else needle in text
        if matched:
            out.append(ClinicalConcept(ORGAN, structure, "abnormality", "absent",
                                        _certainty(text), "generic_explicit_normal"))
    return out


_EXTRACTORS = [
    _extract_meniscus,
    _extract_cruciate_ligaments,
    _extract_collateral_ligaments,
    _extract_combined_ligaments_normal,
    _extract_chondropathy,
    _extract_effusion,
    _extract_cysts,
    _extract_bone_marrow_edema,
    _extract_tendinopathy,
]


def extract_concepts(text_normalized: str) -> ConceptExtractionResult:
    """text_normalized: ja em minusculas / espacos colapsados
    (backend.normalization.text_normalization.normalized)."""
    concepts: list[ClinicalConcept] = []
    for extractor in _EXTRACTORS:
        concepts.extend(extractor(text_normalized))

    covered_structures = {c.structure for c in concepts}
    concepts.extend(_extract_generic_normal(text_normalized, covered_structures))

    return ConceptExtractionResult(concepts=concepts)
