"""Traducoes PT-BR para exibicao — fonte unica usada pela API (e por
qualquer interface), para nao duplicar rotulos em frontend e backend.

Chaves sao exatamente os codigos internos usados em
backend/clinical/knee_concepts.py. Um codigo sem tradução cadastrada
cai no fallback (`_fallback_label`), nunca quebra a exibição.
"""

from __future__ import annotations

STRUCTURE_LABELS = {
    "meniscus_medial": "Menisco medial",
    "meniscus_lateral": "Menisco lateral",
    "acl": "Ligamento cruzado anterior (LCA)",
    "pcl": "Ligamento cruzado posterior (LCP)",
    "mcl": "Ligamento colateral medial (LCM)",
    "lcl": "Ligamento colateral lateral (LCL)",
    "knee_joint": "Articulação (compartimentos)",
    "joint_space": "Espaço articular",
    "baker_cyst": "Cisto poplíteo (Baker)",
    "parameniscal_cyst": "Cisto parameniscal",
    "ganglion_cyst": "Cisto gangliônico",
    "bone": "Osso",
    "quadriceps_tendon": "Tendão do quadríceps",
    "patellar_tendon": "Tendão patelar",
    "tendon_unspecified": "Tendão (não especificado)",
    "patella": "Patela",
    "retinaculum": "Complexo retinacular",
}

FINDING_LABELS = {
    "tear": "Rotura",
    "degeneration": "Degeneração",
    "injury": "Lesão/espessamento",
    "chondropathy": "Condropatia",
    "degenerative_arthropathy": "Artropatia degenerativa",
    "effusion": "Derrame articular",
    "cyst": "Cisto",
    "bone_marrow_edema": "Edema ósseo/medular",
    "insufficiency_fracture": "Fratura por insuficiência",
    "tendinopathy": "Tendinopatia",
    "abnormality": "Alteração",
}

STATUS_LABELS = {"present": "Presente", "absent": "Ausente"}

LOCATION_LABELS = {
    "posterior_horn": "Corno posterior",
    "anterior_horn": "Corno anterior",
    "body": "Corpo",
    "patellofemoral": "Compartimento patelofemoral",
    "medial_femorotibial": "Compartimento femorotibial medial",
    "lateral_femorotibial": "Compartimento femorotibial lateral",
    "femorotibial_unspecified": "Compartimento femorotibial (não especificado)",
    "tricompartmental": "Tricompartimental",
    "tibiofibular": "Compartimento tibiofibular",
}

_SEVERITY_WORD_LABELS = {
    "leve": "leve", "discreto": "discreto", "moderado": "moderado",
    "acentuado": "acentuado", "importante": "importante", "volumoso": "volumoso",
    "pequeno": "pequeno", "mínimo": "mínimo", "incipiente": "incipiente",
    "complete": "completa", "partial": "parcial", "near_complete": "quase completa",
}


def _fallback_label(code: str | None) -> str:
    if not code:
        return ""
    return code.replace("_", " ").strip().capitalize()


def structure_label(code: str) -> str:
    return STRUCTURE_LABELS.get(code, _fallback_label(code))


def finding_label(code: str) -> str:
    return FINDING_LABELS.get(code, _fallback_label(code))


def status_label(code: str) -> str:
    return STATUS_LABELS.get(code, _fallback_label(code))


def location_label(code: str | None) -> str:
    if not code:
        return ""
    return LOCATION_LABELS.get(code, _fallback_label(code))


def severity_label(severity: str | None) -> str:
    """Formata severity para exibicao — pode ser um token simples
    ('leve'), um grau ('grade_2'), uma faixa ('grade_1_2') ou uma
    combinacao ('leve|grade_2_3'), ver knee_concepts.py."""
    if not severity:
        return ""
    parts = []
    for token in severity.split("|"):
        if token.startswith("grade_"):
            grades = token.removeprefix("grade_").split("_")
            parts.append("grau " + "/".join(grades))
        else:
            parts.append(_SEVERITY_WORD_LABELS.get(token, _fallback_label(token)))
    return ", ".join(parts)
