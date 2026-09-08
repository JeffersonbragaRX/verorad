"""Lexico clinico derivado do corpus — Fase 4B (base).

Substitui a ideia inviavel de escrever um extrator por tipo de exame
(seriam 210). Aqui o vocabulario e' MINERADO do proprio corpus e cada
termo carrega a evidencia que sustenta sua classificacao, mais o
METODO usado — porque os metodos tem forca epistemica diferente e a
especificacao exige distinguir fato observado de inferencia.

Metodos de classificacao, do mais forte ao mais fraco:

  corpus_positional  — estatistica posicional medida no corpus.
                       'P(precedido de preposicao)' alto identifica
                       anatomia com boa precisao ('do manguito', 'do
                       labro', 'do tarso'); 'P(apos sinais de/area de)'
                       alto identifica achado ('sinais de sinovite').
                       Medido, nao suposto.
  morphological      — sufixo morfologico do portugues medico
                       (-patia, -ite, -ose, -oma, -ectasia...). Regular
                       o bastante para ser usado, mas e' regra de forma,
                       nao evidencia de uso.
  model_knowledge    — conhecimento medico do modelo, para nucleos
                       anatomicos e achados de alta frequencia que os
                       sinais acima nao resolvem. E' INFERENCIA, nao
                       observacao: fica marcado como tal e vai para
                       revisao.

NENHUM termo aqui esta clinicamente validado. Todo registro nasce com
validation_status='extraction_candidate'. So o radiologista promove
para 'validated_clinically' (secao 15 do prompt mestre).

Limitacao conhecida e medida: inicio de clausula NAO separa anatomia de
achado em portugues radiologico — 'Rins de dimensoes normais' e
'Condropatia femoropatelar' abrem a frase do mesmo jeito. Por isso esse
sinal nao e' usado como criterio de classificacao, apenas registrado
como evidencia.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

LEXICON_VERSION = "lexicon/1.0.0"

# --------------------------------------------------------------------
# Morfologia do portugues medico
# --------------------------------------------------------------------
# Sufixos que caracterizam ACHADO (processo/doenca/alteracao).
_FINDING_SUFFIXES = (
    "patia", "patias", "ite", "ites", "ose", "oses", "oma", "omas",
    "megalia", "algia", "algias", "plasia", "plasias", "trofia", "trofias",
    "estenose", "estenoses", "lise", "lises", "cele", "celes",
    "ectasia", "ectasias", "edema", "edemas", "fratura", "fraturas",
    "rotura", "roturas", "ruptura", "rupturas", "lesao", "lesoes",
    "cisto", "cistos", "nodulo", "nodulos", "derrame", "derrames",
    "espessamento", "espessamentos", "abaulamento", "abaulamentos",
    "protrusao", "protrusoes", "hernia", "hernias", "hernia", "esclerose",
    "calcificacao", "calcificacoes", "ossificacao", "ossificacoes",
    "degeneracao", "degeneracoes", "inflamacao", "hemorragia", "hemorragias",
    "isquemia", "infarto", "infartos", "trombose", "tromboses",
    "aneurisma", "aneurismas", "fissura", "fissuras", "erosao", "erosoes",
    "listese", "listeses", "sinovite", "bursite", "tendinopatia",
    "condropatia", "artropatia", "atrofia", "hipertrofia", "hiperplasia",
    "neoplasia", "metastase", "metastases", "consolidacao", "consolidacoes",
    "atelectasia", "atelectasias", "enfisema", "granuloma", "granulomas",
    "esteatose", "cirrose", "ascite", "hidronefrose", "litiase",
    "espondilolistese", "espondiloartrose", "osteoartrose", "osteofito",
    "osteofitos", "sinusopatia", "mastoidopatia", "gonartrose", "coxartrose",
)

# Sufixos/palavras que caracterizam ATRIBUTO (gravidade, morfologia,
# distribuicao) — nao sao achado nem estrutura.
# Os tres eixos abaixo eram uma lista unica de 'atributo'. Medido na
# saida real, isso colocava 'bilateral' (lateralidade) e 'parcial'
# (extensao) no campo `severity` do conceito — campos distintos no
# schema universal (secao 7) colapsados num so. Separados por eixo.
_SEVERITY_TERMS = {
    "leve", "leves", "moderado", "moderada", "moderados", "moderadas",
    "acentuado", "acentuada", "acentuados", "acentuadas",
    "discreto", "discreta", "discretos", "discretas",
    "importante", "importantes", "pequeno", "pequena", "pequenos", "pequenas",
    "minimo", "minima", "minimos", "minimas", "incipiente", "incipientes",
    "grande", "grandes", "volumoso", "volumosa", "extenso", "extensa",
    "severo", "severa", "intenso", "intensa", "significativo", "significativa",
    "acentuadamente", "levemente", "discretamente", "moderadamente",
}

_MORPHOLOGY_TERMS = {
    "nodular", "nodulares", "cistico", "cistica", "solido", "solida",
    "heterogeneo", "heterogenea", "homogeneo", "homogenea",
    "irregular", "irregulares", "regular", "regulares", "circunscrito",
    "circunscrita", "lobulado", "lobulada", "espiculado", "espiculada",
    "linear", "lineares", "multiloculado", "septado", "septada",
    "vegetante", "exofitico", "exofitica", "sesil", "pediculado",
    "arredondado", "arredondada", "ovalado", "ovalada", "alongado",
    "parcial", "parciais", "completo", "completa", "transfixante",
    "transfixantes", "horizontal", "vertical", "obliqua", "obliquo",
}

_DISTRIBUTION_TERMS = {
    "focal", "focais", "difuso", "difusa", "difusos", "difusas",
    "esparso", "esparsos", "esparsa", "esparsas", "multiplo", "multiplos",
    "multipla", "multiplas", "unico", "unica", "confluente", "confluentes",
    "segmentar", "lobar", "generalizado", "generalizada", "localizado",
    "localizada", "simetrico", "simetrica", "assimetrico", "assimetrica",
    "central", "periferico", "periferica", "superficial", "profundo",
    "profunda", "proximal", "distal", "cranial", "caudal", "ventral",
    "dorsal", "apical", "basal", "subcortical", "subcondral",
    "intrassubstancial", "insercional", "anterior", "posterior",
    "superior", "inferior", "medial", "lateral",
}

# Palavras que NAO sao anatomia mesmo aparecendo depois de preposicao
# (o sinal posicional as classificaria como estrutura). Sao termos de
# tecnica, meta-laudo ou partitivos genericos, observados na saida real.
_NON_ANATOMY_BLOCKLIST = {
    "sequencia", "sequencias", "tecnica", "tecnicas", "protocolo", "aquisicao",
    "incidencia", "incidencias", "plano", "planos", "corte", "cortes",
    "metodo", "metodos", "laudo", "laudos", "estudo", "estudos", "exame",
    "exames", "normalidade", "presente", "presentes", "mecanismo",
    "redor", "porcao", "porcoes", "regiao", "regioes", "nivel", "niveis",
    "grau", "graus", "caso", "casos", "peso", "situacao", "importancia",
    "controle", "avaliacao", "analise", "acima", "abaixo", "meio",
    "vista", "correlacao", "seguimento", "referencia", "valores",
}

# Nucleos anatomicos genericos (conhecimento medico do modelo). Nao
# cobrem toda a anatomia — cobrem os NUCLEOS que se combinam com
# modificadores no corpus ('ligamento cruzado anterior', 'tendao do
# supraespinal'). Marcados como model_knowledge.
_ANATOMY_HEADS = {
    "ligamento", "ligamentos", "tendao", "tendoes", "musculo", "musculos",
    "osso", "ossos", "articulacao", "articulacoes", "menisco", "meniscos",
    "cartilagem", "labro", "bursa", "nervo", "nervos", "raiz", "raizes",
    "disco", "discos", "vertebra", "vertebras", "corpo", "corpos",
    "medula", "canal", "forame", "forames", "saco", "artéria", "arteria",
    "arterias", "veia", "veias", "vaso", "vasos", "aorta", "coronaria",
    "coronarias", "ventriculo", "ventriculos", "atrio", "valva", "miocardio",
    "pericardio", "pulmao", "pulmoes", "lobo", "lobos", "segmento",
    "bronquio", "bronquios", "traqueia", "pleura", "mediastino", "hilo",
    "figado", "baco", "pancreas", "rim", "rins", "adrenal", "adrenais",
    "vesicula", "ducto", "duto", "colon", "intestino", "estomago",
    "bexiga", "prostata", "utero", "ovario", "ovarios", "endometrio",
    "miometrio", "colo", "vagina", "testiculo", "mama", "mamas",
    "encefalo", "cerebro", "cerebelo", "tronco", "hipofise", "sela",
    "ventriculo", "sulco", "sulcos", "giro", "giros", "substancia",
    "cortex", "seio", "seios", "orbita", "orbitas", "tireoide",
    "linfonodo", "linfonodos", "parenquima", "cortical", "medular",
    "patela", "femur", "tibia", "fibula", "umero", "radio", "ulna",
    "escapula", "clavicula", "acromio", "coracoide", "calcaneo", "talus",
    "carpo", "tarso", "falange", "falanges", "metacarpo", "metatarso",
    "quadril", "joelho", "ombro", "cotovelo", "punho", "tornozelo",
    "coluna", "sacro", "coccix", "ilíaco", "iliaco", "acetabulo",
    "manguito", "supraespinal", "supraespinhal", "infraespinal",
    "subescapular", "biceps", "triceps", "quadriceps", "gluteo", "gluteos",
    "plato", "condilo", "condilos", "troclea", "epicondilo", "maleolo",
    "aquiles", "fascia", "aponeurose", "retinaculo", "capsula", "sinovia",
    "plexo", "plexos", "duramater", "espaco", "espacos", "recesso",
}

# DESCRITOR: a PROPRIEDADE que esta sendo afirmada sobre a estrutura
# ('Corpos vertebrais com alturas e morfologia preservadas'). Nao e'
# achado nem estrutura — e' o eixo sobre o qual o achado/normalidade e'
# declarado. Categoria acrescentada depois de medir: sem ela, os termos
# de maior frequencia do corpus ('sinal' 10.345x, 'morfologia' 7.901x)
# caiam todos em 'unclassified', escondendo que sao um tipo proprio.
_DESCRIPTOR_TERMS = {
    "sinal", "sinais", "intensidade", "hipersinal", "hipossinal",
    "morfologia", "morfologias", "dimensao", "dimensoes", "tamanho",
    "contorno", "contornos", "limite", "limites", "margem", "margens",
    "espessura", "espessuras", "altura", "alturas", "calibre", "calibres",
    "textura", "densidade", "densidades", "atenuacao", "coeficiente",
    "volume", "volumes", "peso", "topografia", "posicao", "posicionamento",
    "alinhamento", "amplitude", "trofismo", "realce", "impregnacao",
    "captacao", "perfusao", "difusao", "restricao", "ecogenicidade",
    "estrutura", "estruturas", "arquitetura", "configuracao", "superficie",
    "superficies", "diferenciacao", "transicao", "conteudo", "aspecto",
    "alteracao", "alteracoes", "achado", "achados",
}

# Sufixos adjetivais que, em portugues radiologico, formam MODIFICADOR
# (qualifica uma estrutura ou um achado: 'discal', 'articular',
# 'vertebrais', 'degenerativa'). Nao sao achados por si sos — 'discal'
# nao diz o que ha' no disco.
_MODIFIER_SUFFIXES = (
    "al", "ais", "ar", "ares", "ico", "ica", "icos", "icas",
    "ivo", "iva", "ivos", "ivas", "oso", "osa", "osos", "osas",
    "ano", "ana", "anos", "anas", "eo", "ea", "eos", "eas",
)

# Lateralidade e' resolvida pelo clause engine (por posicao, com
# escopo). Nao deve virar termo de lexico.
_LATERALITY_WORDS = {
    "direita", "direito", "direitos", "direitas",
    "esquerda", "esquerdo", "esquerdos", "esquerdas",
}

_STOPWORDS = set("""a o as os um uma uns umas de do da dos das em no na nos nas por para com sem
e ou que se ao aos pelo pela pelos pelas entre sobre sob ate apos antes tambem mais menos muito
pouco seu sua seus suas este esta estes estas esse essa esses essas isso aquele aquela ha nao sim
ser estar tem foi sao eram apresenta apresentam observa observam observado observada nota notam
notado evidencia evidenciam evidenciado demais outros outras outro outra qual quais cujo cuja
quando onde como porem mas contudo entretanto sendo ficando mostrando associado associada
associados associadas nivel niveis cerca aproximadamente medindo mede maior menor bem mal
seguinte seguintes presenca ausencia caso casos estudo exame atual anterior aspecto aspectos
padrao tipo forma formas natureza carater vista visto vistos habitual habituais preservado
preservada preservados preservadas integro integra integros integras normal normais""".split())

# Gerundio e particípio: formas verbais, nao termos clinicos. Excecoes
# necessarias porque varios ACHADOS reais terminam igual a particípio
# ('espessamento' nao, mas 'consolidado'/'calcificado' descrevem
# estado). Mantidas de fora as que ja foram classificadas antes deste
# passo (a ordem das regras protege esses casos).
_VERB_FORM_RE = re.compile(r"(ando|endo|indo)$")

_WORD_RE = re.compile(r"[a-zà-ÿ]+")
_PREPOSITIONS = {"do", "da", "dos", "das", "no", "na", "nos", "nas", "em",
                  "ao", "aos", "pelo", "pela", "junto", "adjacente"}
_FINDING_TRIGGERS = {"sinais", "presenca", "area", "areas", "foco", "focos",
                      "imagem", "imagens", "processo", "quadro"}


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text)
                    if unicodedata.category(c) != "Mn")


@dataclass
class LexiconEntry:
    term: str
    term_type: str            # anatomy | finding | attribute | unclassified
    method: str               # corpus_positional | morphological | model_knowledge
    confidence: float
    frequency: int
    n_exam_types: int
    top_exam_type: str
    concentration: float      # fracao no exam_type dominante
    p_after_preposition: float
    p_clause_initial: float
    p_after_finding_trigger: float
    domains: list[str] = field(default_factory=list)
    validation_status: str = "extraction_candidate"
    lexicon_version: str = LEXICON_VERSION


def _classify(term: str, ev: dict) -> tuple[str, str, float]:
    """Retorna (tipo, metodo, confianca). Ordem = forca do sinal."""
    words = term.split()
    # NUCLEO = PRIMEIRA palavra. Em portugues o substantivo vem antes do
    # adjetivo ('abaulamento discal', 'derrame articular', 'artropatia
    # degenerativa'): o nucleo e' 'abaulamento', nao 'discal'. Usar a
    # ultima palavra (regra do ingles) deixava justamente os termos
    # compostos mais frequentes do corpus sem classificacao, e' um bug
    # de linguagem, nao uma lacuna de cobertura.
    head = words[0]
    tail = words[-1]

    # -1) Formas verbais nao sao termos de lexico clinico ('tocando',
    #     'apresentando', 'descritos'). Filtradas para nao poluirem a
    #     cauda nao modelada, que precisa listar lacunas REAIS.
    if len(words) == 1 and _VERB_FORM_RE.search(head):
        return "verb_form", "morphological", 0.60

    # 0) Lateralidade e' resolvida por posicao no clause engine.
    if any(w in _LATERALITY_WORDS for w in words):
        return "laterality_handled_by_clause_engine", "corpus_positional", 1.0

    # 0b) Termos de tecnica/meta-laudo nunca sao anatomia, mesmo com
    #     sinal posicional forte ('do metodo', 'da sequencia').
    if head in _NON_ANATOMY_BLOCKLIST and len(words) == 1:
        return "non_clinical", "model_knowledge", 0.60

    # 1) Atributo, por eixo — severidade, morfologia e distribuicao sao
    #    campos DIFERENTES no schema universal e nao podem ser
    #    colapsados num campo so.
    if len(words) == 1 and term in _SEVERITY_TERMS:
        return "severity", "model_knowledge", 0.75
    if len(words) == 1 and term in _MORPHOLOGY_TERMS:
        return "morphology", "model_knowledge", 0.75
    if len(words) == 1 and term in _DISTRIBUTION_TERMS:
        return "distribution", "model_knowledge", 0.75

    # 1b) Descritor: a propriedade afirmada sobre a estrutura.
    if head in _DESCRIPTOR_TERMS:
        return "descriptor", "model_knowledge", 0.75

    # 2) Morfologia de achado — sufixo regular do portugues medico.
    if any(head.endswith(sfx) for sfx in _FINDING_SUFFIXES):
        return "finding", "morphological", 0.80

    # 3) Estatistica posicional medida (o sinal mais forte que temos).
    if ev["p_after_preposition"] >= 0.85 and ev["frequency"] >= 30:
        return "anatomy", "corpus_positional", 0.80
    if ev["p_after_finding_trigger"] >= 0.30 and ev["frequency"] >= 30:
        return "finding", "corpus_positional", 0.70

    # 4) Nucleo anatomico conhecido (inferencia do modelo).
    if head in _ANATOMY_HEADS or words[0] in _ANATOMY_HEADS:
        return "anatomy", "model_knowledge", 0.65

    # 5) Sinal posicional mais fraco, ainda informativo.
    if ev["p_after_preposition"] >= 0.60:
        return "anatomy", "corpus_positional", 0.55

    # 6) Modificador adjetival (qualifica estrutura ou achado, nao e' um
    #    achado por si so: 'discal' nao diz o que ha' no disco).
    if len(words) == 1 and any(head.endswith(sfx) for sfx in _MODIFIER_SUFFIXES):
        return "modifier", "morphological", 0.55

    # 7) Composto cujo modificador e' adjetival mas o nucleo nao foi
    #    reconhecido: ainda e' um termo composto util, classificado pelo
    #    que da' para sustentar — nucleo desconhecido, forma conhecida.
    if len(words) > 1 and any(tail.endswith(sfx) for sfx in _MODIFIER_SUFFIXES):
        return "unclassified_compound", "morphological", 0.30

    return "unclassified", "none", 0.0


def mine_lexicon(conn: sqlite3.Connection, min_frequency: int = 20,
                  max_ngram: int = 3) -> list[LexiconEntry]:
    """Minera o vocabulario das secoes clinicas (findings/impression).

    Trabalha sobre text_normalized ja persistido, entao a mineracao e'
    reproduzivel a partir do banco — nao depende de reprocessar o RAW."""
    rows = conn.execute("""
        SELECT s.text_normalized, r.exam_type, r.domain
        FROM sentences s
        JOIN report_sections rs ON s.section_id = rs.id
        JOIN reports r ON s.report_id = r.id
        WHERE rs.section_type IN ('findings','impression')
    """).fetchall()

    total = Counter()
    by_exam: dict[str, Counter] = defaultdict(Counter)
    by_domain: dict[str, set] = defaultdict(set)
    after_prep = Counter()
    clause_initial = Counter()
    after_trigger = Counter()

    for text, exam_type, domain in rows:
        norm = strip_accents(text.lower())
        for clause in re.split(r"[,;:.]", norm):
            words = _WORD_RE.findall(clause)
            for i, word in enumerate(words):
                prev = words[i - 1] if i > 0 else None
                prev2 = words[i - 2] if i > 1 else None
                for n in range(1, max_ngram + 1):
                    if i + n > len(words):
                        break
                    gram_words = words[i:i + n]
                    if gram_words[0] in _STOPWORDS or gram_words[-1] in _STOPWORDS:
                        continue
                    if any(len(w) <= 3 for w in gram_words):
                        continue
                    gram = " ".join(gram_words)
                    total[gram] += 1
                    by_exam[gram][exam_type] += 1
                    by_domain[gram].add(domain)
                    if i == 0:
                        clause_initial[gram] += 1
                    if prev in _PREPOSITIONS:
                        after_prep[gram] += 1
                    if prev in _FINDING_TRIGGERS or (prev == "de" and prev2 in _FINDING_TRIGGERS):
                        after_trigger[gram] += 1

    entries: list[LexiconEntry] = []
    for term, freq in total.items():
        if freq < min_frequency:
            continue
        exams = by_exam[term]
        top_exam, top_n = exams.most_common(1)[0]
        ev = {
            "frequency": freq,
            "p_after_preposition": after_prep[term] / freq,
            "p_clause_initial": clause_initial[term] / freq,
            "p_after_finding_trigger": after_trigger[term] / freq,
        }
        term_type, method, confidence = _classify(term, ev)
        entries.append(LexiconEntry(
            term=term, term_type=term_type, method=method, confidence=confidence,
            frequency=freq, n_exam_types=len(exams), top_exam_type=top_exam,
            concentration=top_n / freq,
            p_after_preposition=round(ev["p_after_preposition"], 3),
            p_clause_initial=round(ev["p_clause_initial"], 3),
            p_after_finding_trigger=round(ev["p_after_finding_trigger"], 3),
            domains=sorted(by_domain[term]),
        ))

    entries.sort(key=lambda e: -e.frequency)
    return entries
