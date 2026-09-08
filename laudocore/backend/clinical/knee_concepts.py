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
# Captura faixas de grau ('grau I/II', 'grau II/III') alem de grau unico.
# Bug real encontrado em revisao manual: 'grau I/II' era truncado para
# apenas 'grade_1', perdendo o limite superior da faixa — informacao
# clinicamente relevante (grau indeterminado entre I e II nao e o
# mesmo que grau I puro).
_GRADE_RE = re.compile(r"grau\s*(i{1,3}v?|iv|[1-4])(?:\s*[/\-]\s*(i{1,3}v?|iv|[1-4]))?\b")

_ROMAN_TO_ARABIC = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}


def _has_any(text: str, needles: list[str]) -> bool:
    return any(n in text for n in needles)


# Frases que identificam uma estrutura/achado distinto, usadas por
# _segment_containing para saber ONDE parar de estender o escopo de uma
# clausula — ou seja, o sinal de que a virgula seguinte introduziu uma
# estrutura DIFERENTE, nao apenas mais um qualificador da mesma.
_KNOWN_STRUCTURE_PHRASES = [
    "menisco medial", "menisco lateral", "menisco", "meniscal",
    "ligamento cruzado anterior", "ligamento cruzado posterior",
    "ligamento colateral medial", "ligamento colateral lateral",
    "condropatia", "artropatia degenerativa",
    "fissura condral", "fissuras condrais",
    "cisto poplíteo", "cisto de baker", "cisto parameniscal", "cisto gangliônico",
    "edema ósseo", "edema osseo", "edema medular", "edema subcondral",
    "fratura por insuficiência", "fratura de insuficiência", "fraturas por insuficiência",
    "tendinopatia", "tendão quadríceps", "tendão do quadríceps", "tendão patelar",
    "derrame articular", "patela",
]


def _segment_containing(text: str, phrase: str) -> str:
    """Retorna o(s) segmento(s) (separados por virgula/ponto-e-virgula)
    relevantes a estrutura identificada por 'phrase', para escopar
    negacao/severidade aquele trecho em vez da sentenca inteira.

    Bug real (auditoria externa + revisao propria, confirmado no
    corpus): negacao/severidade eram checadas na sentenca INTEIRA, entao
    uma clausula sobre OUTRA estrutura contaminava a atual — ex.:
    'Rotura do ligamento cruzado anterior, sem lesão meniscal.' negava o
    LCA por causa de 'sem lesão' numa clausula sobre o menisco; 'Menisco
    medial sem roturas, observando-se lesão do menisco lateral.' negava
    os dois meniscos por causa de 'sem roturas' dito so sobre o medial.

    Estrategia: comeca no primeiro segmento que contem 'phrase' e
    ESTENDE para os segmentos seguintes ate encontrar um que mencione
    outra estrutura conhecida (_KNOWN_STRUCTURE_PHRASES) — assim
    'ligamento cruzado posterior verticalizado, porém íntegro.'
    (qualificador da MESMA estrutura, so separado por virgula) continua
    visivel inteiro, mas uma clausula sobre outra estrutura para de
    contaminar. Se nenhuma outra estrutura conhecida aparecer no texto,
    nao ha risco de contaminacao identificavel — devolve o texto
    inteiro (mais seguro do que arriscar cortar um qualificador da
    propria estrutura). Heuristica de pontuacao, nao um parser
    sintatico completo — permanece uma limitacao conhecida para
    coordenacoes sem virgula."""
    other_phrases = [p for p in _KNOWN_STRUCTURE_PHRASES
                      if p != phrase and p not in phrase and phrase not in p]
    if not any(op in text for op in other_phrases):
        return text
    segments = re.split(r"[,;]", text)
    start = None
    for i, seg in enumerate(segments):
        if phrase in seg:
            start = i
            break
    if start is None:
        return text
    scoped = [segments[start]]
    for seg in segments[start + 1:]:
        if any(op in seg for op in other_phrases):
            break
        scoped.append(seg)
    return ",".join(scoped)


def _negated_near(scope: str, trigger_phrase: str) -> bool:
    """Negacao mais ampla que _NEGATION_CUES, para achados cuja negacao
    tipica no corpus e simplesmente 'sem <achado>' ou 'sem <filler>
    <achado>' (ex.: 'sem edema subcondral', 'sem focos de edema
    ósseo'), sem usar nenhuma das frases compostas de _NEGATION_CUES
    (que foram curadas para rotura/lesao de menisco e ligamentos, nao
    para este padrao). Usa fronteira de palavra em 'sem' (para nao
    confundir com 'sempre') e tolera ate 3 palavras de preenchimento
    entre 'sem' e o inicio da frase-gatilho."""
    if _has_any(scope, _NEGATION_CUES):
        return True
    idx = scope.find(trigger_phrase)
    if idx == -1:
        return False
    before = scope[:idx]
    return re.search(r"\bsem\b(\s+\w+){0,3}\s*$", before) is not None


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
    g1 = _ROMAN_TO_ARABIC.get(m.group(1), m.group(1))
    if m.group(2):
        g2 = _ROMAN_TO_ARABIC.get(m.group(2), m.group(2))
        return f"{g1}_{g2}"
    return g1


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
    structures = []
    if "menisco medial" in text:
        structures.append(("meniscus_medial", "menisco medial"))
    if "menisco lateral" in text:
        structures.append(("meniscus_lateral", "menisco lateral"))
    if not structures and "meniscos" in text:
        structures = [("meniscus_medial", "meniscos"), ("meniscus_lateral", "meniscos")]
    if not structures:
        return out

    tear_kw = ["rotura", "lesão", "lesao", "fissura", "ruptura", "amputação"]
    degeneration_kw = ["degeneração", "degeneracao", "degenerativ"]
    degeneration_negation_kw = [
        "sem degeneração", "sem sinais de degeneração", "sem alterações degenerativas",
    ]

    # Bug real (auditoria externa, confirmado no corpus): 'Menisco
    # medial sem roturas, observando-se lesão do menisco lateral.'
    # marcava OS DOIS meniscos como sem rotura, porque negacao/keyword
    # eram checados na sentenca inteira em vez de por lado. Cada
    # estrutura agora usa seu proprio segmento (_segment_containing).
    for structure, phrase in structures:
        scope = _segment_containing(text, phrase)
        has_tear_kw = _has_any(scope, tear_kw)
        has_degeneration_kw = _has_any(scope, degeneration_kw)
        negated = _has_any(scope, _NEGATION_CUES)
        explicit_normal = _has_any(scope, _NORMAL_STATUS_WORDS) or "sem evidências de lesões" in scope

        location = None
        if "corno posterior" in scope:
            location = "posterior_horn"
        elif "corno anterior" in scope:
            location = "anterior_horn"
        elif "corpo do menisco" in scope or "corpo meniscal" in scope:
            location = "body"

        # tear e degeneracao sao EIXOS INDEPENDENTES — uma estrutura pode
        # estar degenerada e, ao mesmo tempo, sem rotura (achado real e
        # frequente: 'Degeneração difusa do menisco lateral, sem roturas.').
        # Tratar como if/elif (como numa versao anterior) fazia essa frase
        # composta parecer uma frase 'limpa' de 1 conceito so, o que
        # confundia o banco de frases do Report Compiler (Fase 6) na hora
        # de escolher frases reutilizaveis sem conteudo extra nao pedido.
        degeneration_negated = _has_any(scope, degeneration_negation_kw)

        if has_tear_kw and negated:
            out.append(ClinicalConcept(ORGAN, structure, "tear", "absent",
                                        _certainty(scope), "meniscus_tear_negated",
                                        location=location))
        elif has_tear_kw and not negated:
            out.append(ClinicalConcept(ORGAN, structure, "tear", "present",
                                        _certainty(scope), "meniscus_tear",
                                        location=location))
        elif explicit_normal:
            out.append(ClinicalConcept(ORGAN, structure, "tear", "absent",
                                        _certainty(scope), "meniscus_explicit_normal",
                                        location=location))

        if has_degeneration_kw and not degeneration_negated:
            out.append(ClinicalConcept(ORGAN, structure, "degeneration", "present",
                                        _certainty(scope), "meniscus_degeneration",
                                        severity=_first_severity(scope), location=location))
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
        # 'verticalizad' NAO entra aqui: e um descritor morfologico/posicional,
        # nao implica degeneracao por si so (bug real encontrado em revisao
        # manual — 'Ligamento cruzado posterior verticalizado, porém íntegro.'
        # foi indevidamente marcado como degeneracao=present sem a palavra
        # 'degeneração' aparecer na frase).
        degeneration_kw = ["degeneração", "degeneracao", "degenerativ"]

        # Bug real (auditoria externa, confirmado no corpus): 'Rotura do
        # ligamento cruzado anterior, sem lesão meniscal.' marcava o LCA
        # como AUSENTE, porque 'negated' checava a sentenca inteira e
        # 'sem lesão' (sobre o menisco, na outra clausula) contaminava o
        # LCA. Escopar ao segmento que contem a frase da estrutura.
        scope = _segment_containing(text, phrase)
        negated = _has_any(scope, _NEGATION_CUES)
        has_rupture = _has_any(scope, rupture_kw)
        has_degeneration = _has_any(scope, degeneration_kw)
        explicit_normal = _has_any(scope, _NORMAL_STATUS_WORDS)

        # 'praticamente completa'/'quase completa' NAO e' o mesmo que
        # 'completa' — bug real encontrado em revisao manual (severidade
        # relatada como 'complete' quando o texto qualificava como quase
        # completa). Checa o qualificador de aproximacao ANTES do termo
        # bruto para nao superestimar a gravidade. Escopado ao segmento
        # para nao atribuir a severidade do LCP ao LCA quando os dois
        # aparecem na mesma sentenca com graus diferentes.
        near_complete = _has_any(scope, ["praticamente completa", "quase completa"])
        if near_complete:
            severity = "near_complete"
        elif "completa" in scope:
            severity = "complete"
        elif "parcial" in scope:
            severity = "partial"
        else:
            severity = None

        # tear e degeneracao sao eixos independentes (mesmo raciocinio
        # do menisco: 'verticalizado, com degeneração difusa, sem
        # roturas' descreve os dois ao mesmo tempo).
        if has_rupture and negated:
            out.append(ClinicalConcept(ORGAN, structure, "tear", "absent",
                                        _certainty(scope), f"{structure}_tear_negated"))
        elif has_rupture and not negated:
            out.append(ClinicalConcept(ORGAN, structure, "tear", "present",
                                        _certainty(scope), f"{structure}_tear",
                                        severity=severity))
        elif explicit_normal:
            out.append(ClinicalConcept(ORGAN, structure, "tear", "absent",
                                        _certainty(scope), f"{structure}_explicit_normal"))

        if has_degeneration:
            out.append(ClinicalConcept(ORGAN, structure, "degeneration", "present",
                                        _certainty(scope), f"{structure}_degeneration"))
    return out


def _extract_collateral_ligaments(text: str) -> list[ClinicalConcept]:
    out = []
    for phrase, structure in [
        ("ligamento colateral medial", "mcl"),
        ("ligamento colateral lateral", "lcl"),
    ]:
        if phrase not in text:
            continue
        # rotura (tear/injury) e espessamento/degeneracao intersticial
        # (alteracao cronica, sem rotura franca) sao EIXOS INDEPENDENTES
        # — mesmo bug ja corrigido para menisco e ligamentos cruzados.
        # Bug real encontrado em revisao manual: 'Degeneração intersticial
        # das fibras... sem sinais de ruptura.' e 'Espessamento cicatricial
        # do ligamento colateral medial, sem roturas.' descrevem uma
        # alteracao CRONICA REAL (presente), mas eram classificadas como
        # injury=ABSENT so porque a rotura aguda foi negada — suprimindo
        # o achado real que a frase afirma.
        rupture_kw = ["rotura", "lesão", "lesao"]
        thickening_kw = ["espessamento", "degeneração intersticial", "degeneracao intersticial"]

        # Mesmo escopo por segmento aplicado a LCA/LCP e menisco — evita
        # que a negacao de uma clausula sobre outra estrutura na mesma
        # sentenca seja atribuida ao ligamento colateral.
        scope = _segment_containing(text, phrase)
        negated = _has_any(scope, _NEGATION_CUES)
        explicit_normal = _has_any(scope, _NORMAL_STATUS_WORDS)
        has_rupture = _has_any(scope, rupture_kw)
        has_thickening = _has_any(scope, thickening_kw)

        if has_rupture and negated:
            out.append(ClinicalConcept(ORGAN, structure, "injury", "absent",
                                        _certainty(scope), f"{structure}_injury_negated"))
        elif has_rupture and not negated:
            out.append(ClinicalConcept(ORGAN, structure, "injury", "present",
                                        _certainty(scope), f"{structure}_injury"))
        elif explicit_normal and not has_thickening:
            out.append(ClinicalConcept(ORGAN, structure, "injury", "absent",
                                        _certainty(scope), f"{structure}_explicit_normal"))

        if has_thickening:
            out.append(ClinicalConcept(ORGAN, structure, "degeneration", "present",
                                        _certainty(scope), f"{structure}_degeneration"))
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


#  Inclui variantes de grafia/acento/hifen REALMENTE observadas no
#  corpus (nao especuladas): 'tíbio-fibular' (vs 'tibiofibular'),
#  'patelo-femoral' (vs 'patelofemoral'), 'fêmorotibial' com circunflexo
#  (provavel erro de digitacao na fonte, mas real) e 'tróclea femoral'
#  (forma nominal, distinta do adjetivo 'troclear' ja tratado como
#  fallback local da condropatia). Bug real encontrado em revisao
#  manual: essas variantes caiam em 'unspecified_compartment' apesar de
#  nomearem o compartimento explicitamente. A logica de deduplicacao em
#  _matched_compartments (por LOCATION resultante, nao por frase) ja
#  cobre essas variantes automaticamente, sem mudanca adicional.
_COMPARTMENTS = [
    ("tricompartimental", "tricompartmental"),
    ("femoropatelar", "patellofemoral"),
    ("patelofemoral", "patellofemoral"),
    ("patelo-femoral", "patellofemoral"),
    ("fêmoro-patelar", "patellofemoral"),
    ("trócleopatelar", "patellofemoral"),
    ("tróclea patelar", "patellofemoral"),
    ("tróclea femoral", "patellofemoral"),
    ("femorotibial medial", "medial_femorotibial"),
    ("fêmorotibial medial", "medial_femorotibial"),
    ("femorotibial lateral", "lateral_femorotibial"),
    ("fêmorotibial lateral", "lateral_femorotibial"),
    ("tibiofibular", "tibiofibular"),
    ("tíbio-fibular", "tibiofibular"),
    ("tibio-fibular", "tibiofibular"),
    ("femorotibial", "femorotibial_unspecified"),
    ("fêmorotibial", "femorotibial_unspecified"),
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


def _matched_compartments(text: str) -> list[str]:
    """Locations distintas mencionadas no texto, sem redundancia.

    Bug real encontrado em revisao manual: 'femorotibial' (generico) e
    substring de 'femorotibial medial'/'femorotibial lateral', entao uma
    frase que so menciona o compartimento ESPECIFICO tambem disparava,
    de forma redundante, um segundo conceito 'femorotibial_unspecified'
    para a MESMA mencao. Corrigido descartando o generico quando o
    especifico da mesma familia ja foi encontrado (e deduplicando por
    location resultante, nao por frase, ja que 'femoropatelar' e
    'patelofemoral' mapeiam para a mesma location e nao devem virar
    dois conceitos)."""
    locations: list[str] = []
    for phrase, location in _COMPARTMENTS:
        if phrase in text and location not in locations:
            locations.append(location)
    if "medial_femorotibial" in locations or "lateral_femorotibial" in locations:
        locations = [loc for loc in locations if loc != "femorotibial_unspecified"]
    return locations


#  'fissura(s) condral(is)' descreve o mesmo tipo de achado que
#  'condropatia' (defeito de cartilagem) sem usar essa palavra — gap de
#  recall real encontrado em revisao manual ('Fissuras condrais
#  profundas...' nao gerava nenhum conceito de condropatia). Tratado
#  como sinonimo de 'condropatia' (nao de 'artropatia degenerativa',
#  que implica doenca articular mais ampla) para fins de finding.
_CHONDRAL_FISSURE_KW = ["fissura condral", "fissuras condrais"]


def _extract_chondropathy(text: str) -> list[ClinicalConcept]:
    out = []
    trigger_kw = ["condropatia"] + _CHONDRAL_FISSURE_KW
    has_chondropathy_kw = _has_any(text, trigger_kw)
    if not has_chondropathy_kw and "artropatia degenerativa" not in text:
        return out
    finding = "chondropathy" if has_chondropathy_kw else "degenerative_arthropathy"

    # Bug real encontrado no corpus (nao fazia parte da auditoria
    # original — achado ao revisar esta rodada de correcao): este
    # extrator nunca checava negacao. 'Não há sinais de condropatia.'
    # virava 'chondropathy present'. Confirmado em sentencas reais do
    # corpus ('não há sinais de condropatia significativa...').
    trigger_phrase = next((kw for kw in trigger_kw if kw in text), "artropatia degenerativa")
    scope = _segment_containing(text, trigger_phrase)
    if _negated_near(scope, trigger_phrase):
        return [ClinicalConcept(ORGAN, "knee_joint", finding, "absent",
                                 _certainty(scope), f"{finding}_negated")]

    grade = _grade(text)
    severity = _first_severity(text)
    matched_locations = _matched_compartments(text)
    matched_any = bool(matched_locations)
    for location in matched_locations:
        out.append(ClinicalConcept(ORGAN, "knee_joint", finding, "present",
                                    _certainty(text), f"{finding}_{location}",
                                    severity=severity, location=location))
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
    seen_structures = set()
    for phrase, structure in [
        ("cisto poplíteo", "baker_cyst"),
        ("cisto de baker", "baker_cyst"),
        ("cisto parameniscal", "parameniscal_cyst"),
        ("cisto gangliônico", "ganglion_cyst"),
    ]:
        if phrase not in text or structure in seen_structures:
            continue
        # Checagem de negacao adicionada nesta rodada de correcao (mesma
        # classe de bug do edema osseo/condropatia abaixo — 0 casos reais
        # observados no corpus atual, mas o extrator nao tinha nenhuma
        # protecao contra 'sem cisto poplíteo').
        scope = _segment_containing(text, phrase)
        if _negated_near(scope, phrase):
            seen_structures.add(structure)
            out.append(ClinicalConcept(ORGAN, structure, "cyst", "absent",
                                        _certainty(scope), "cyst_negated"))
            continue
        # 'not in seen_structures' evita duplicar (bug real encontrado
        # em revisao: 'cisto de baker' e 'cisto poplíteo' sao sinonimos
        # e podem coexistir na mesma frase, gerando 2 conceitos identicos).
        seen_structures.add(structure)
        out.append(ClinicalConcept(ORGAN, structure, "cyst", "present",
                                    _certainty(text), "cyst",
                                    severity=_first_severity(text),
                                    measurement_cm=_measurement_cm(text)))
    return out


def _extract_bone_marrow_edema(text: str) -> list[ClinicalConcept]:
    out = []
    edema_kw = ["edema ósseo", "edema osseo", "edema medular", "edema subcondral"]
    trigger_phrase = next((kw for kw in edema_kw if kw in text), None)
    if trigger_phrase is None:
        return out

    # Bug real encontrado no corpus (nao fazia parte da auditoria
    # original — achado ao revisar esta rodada de correcao): 228 das 730
    # sentencas do corpus que mencionam 'edema subcondral' o fazem
    # negado ('..., sem edema subcondral.'). Este extrator nunca checava
    # negacao — todas viravam 'bone_marrow_edema present'.
    scope = _segment_containing(text, trigger_phrase)
    if _negated_near(scope, trigger_phrase):
        return [ClinicalConcept(ORGAN, "bone", "bone_marrow_edema", "absent",
                                 _certainty(scope), "bone_marrow_edema_negated")]

    location = None
    for phrase, loc in _COMPARTMENTS:
        if phrase in text:
            location = loc
            break
    out.append(ClinicalConcept(ORGAN, "bone", "bone_marrow_edema", "present",
                                _certainty(text), "bone_marrow_edema", location=location))
    return out


# Gap de recall real encontrado em revisao manual: 'Artropatia
# degenerativa tricompartimental com fratura por insuficiência...' so
# gerava o conceito de artropatia, perdendo a fratura por insuficiencia
# citada na mesma frase — um achado clinicamente distinto e relevante
# (risco de colapso subcondral), nao uma variante de artropatia.
def _extract_insufficiency_fracture(text: str) -> list[ClinicalConcept]:
    out = []
    fracture_kw = ["fratura por insuficiência", "fratura de insuficiência",
                   "fraturas por insuficiência"]
    trigger_phrase = next((kw for kw in fracture_kw if kw in text), None)
    if trigger_phrase is None:
        return out

    scope = _segment_containing(text, trigger_phrase)
    if _negated_near(scope, trigger_phrase):
        return [ClinicalConcept(ORGAN, "bone", "insufficiency_fracture", "absent",
                                 _certainty(scope), "insufficiency_fracture_negated")]

    location = None
    for phrase, loc in _COMPARTMENTS:
        if phrase in text:
            location = loc
            break
    out.append(ClinicalConcept(ORGAN, "bone", "insufficiency_fracture", "present",
                                _certainty(text), "insufficiency_fracture", location=location))
    return out


def _extract_tendinopathy(text: str) -> list[ClinicalConcept]:
    out = []
    if "tendinopatia" not in text:
        return out
    scope = _segment_containing(text, "tendinopatia")
    if _negated_near(scope, "tendinopatia"):
        return [ClinicalConcept(ORGAN, "tendon_unspecified", "tendinopathy", "absent",
                                 _certainty(scope), "tendinopathy_negated")]
    if "quadríceps" in scope or "quadriceps" in scope or "quadricipital" in scope:
        structure = "quadriceps_tendon"
    elif "patelar" in scope:
        structure = "patellar_tendon"
    else:
        structure = "tendon_unspecified"
    out.append(ClinicalConcept(ORGAN, structure, "tendinopathy", "present",
                                _certainty(scope), "tendinopathy"))
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

def _extract_generic_normal(text: str, already_covered: set[str]) -> list[ClinicalConcept]:
    out = []
    if not _has_any(text, _NORMAL_STATUS_WORDS):
        return out
    for kind, needle, structure in _GENERIC_NORMAL_STRUCTURES:
        if structure in already_covered:
            continue
        matched = _has_word(text, needle) if kind == "word" else needle in text
        if matched:
            out.append(ClinicalConcept(ORGAN, structure, "abnormality", "absent",
                                        _certainty(text), "generic_explicit_normal"))
    return out


# ---- expansao de coordenacao com elisao ---------------------------------
#
# Bug real encontrado em revisao manual: construcoes como 'ligamento
# cruzado posterior e colateral lateral preservado.' e 'tendões do
# quadríceps e patelar preservados.' citam DUAS estruturas, mas a
# segunda elide o substantivo comum ('ligamento'/'tendão'). Extratores
# que procuram a frase completa ('ligamento colateral lateral') so
# encontram a PRIMEIRA estrutura citada, perdendo a segunda por
# completo — nao e um erro de classificacao, e uma estrutura inteira
# desaparecendo da extracao.
#
# Corrigido de forma GERAL (nao caso a caso): antes de rodar os
# extratores, reescreve o texto reinserindo o substantivo elidido, para
# que as duas estruturas fiquem com a frase completa que os extratores
# ja sabem reconhecer. Isso e normalizacao textual (preserva o
# significado, so torna a elisao explicita), nao inferencia clinica.
_COORDINATION_EXPANSIONS = [
    # 'ligamento cruzado posterior e colateral lateral' -> '... e ligamento colateral lateral'
    (re.compile(
        r"\bligamento (cruzado anterior|cruzado posterior|colateral medial|colateral lateral)"
        r" e (cruzado anterior|cruzado posterior|colateral medial|colateral lateral)\b"
    ), r"ligamento \1 e ligamento \2"),
    # 'tendões do quadríceps e patelar' / 'tendão quadríceps e patelar' -> '... e tendão patelar'
    (re.compile(r"\btend(?:ão|ões)(?: do)? (quadríceps|patelar) e (quadríceps|patelar)\b"),
     r"tendão \1 e tendão \2"),
]


def _expand_elided_coordination(text: str) -> str:
    for pattern, replacement in _COORDINATION_EXPANSIONS:
        text = pattern.sub(replacement, text)
    return text


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
    _extract_insufficiency_fracture,
]


def extract_concepts(text_normalized: str) -> ConceptExtractionResult:
    """text_normalized: ja em minusculas / espacos colapsados
    (backend.normalization.text_normalization.normalized)."""
    text_normalized = _expand_elided_coordination(text_normalized)

    concepts: list[ClinicalConcept] = []
    for extractor in _EXTRACTORS:
        concepts.extend(extractor(text_normalized))

    covered_structures = {c.structure for c in concepts}
    concepts.extend(_extract_generic_normal(text_normalized, covered_structures))

    return ConceptExtractionResult(concepts=concepts)
