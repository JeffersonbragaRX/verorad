"""Clause Engine — Fase 4A, agnostico de dominio.

Resolve, POR ALVO e nao por sentenca inteira: escopo de negacao,
certeza, temporalidade, comparacao, lateralidade local, medidas e
graus. E' a camada que todas as modalidades e tipos de exame
compartilham; nada aqui e' especifico de joelho, coluna ou torax.

Metodologia: adaptacao ao portugues do padrao NegEx/ConText (cue +
direcao + escopo terminado por marcador de fronteira), amplamente
usado em processamento de texto clinico. Isto e' uma ADAPTACAO
propria, nao uma implementacao validada de ConText para portugues —
nao existe validacao publicada citada aqui; a validacao e' a suite
adversarial em tests/test_clause_engine.py, contra padroes reais
observados no corpus.

Por que nao a heuristica anterior: a versao do vertical de joelho
checava negacao na sentenca inteira (e depois em segmentos por
virgula). Isso invertia polaridade em frases coordenadas — 'Rotura do
ligamento cruzado anterior, sem lesao meniscal.' marcava o LCA como
ausente. Aqui a negacao tem posicao, direcao e fronteira explicitas.

Contrato central:
  - Uma CLAUSULA e' um trecho com fronteiras conhecidas.
  - Um CUE (negacao/incerteza/temporalidade/comparacao) tem posicao,
    direcao e um ESCOPO que termina num marcador de fronteira.
  - Um cue so afeta mencoes DENTRO do seu escopo. Nunca a sentenca toda.
  - Nada e' inferido por ausencia: sem cue, o status e' 'present' apenas
    se houver mencao afirmada; ausencia de mencao nunca vira normalidade.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

ENGINE_VERSION = "clause_engine/1.0.0"


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text)
                    if unicodedata.category(c) != "Mn")


def _norm(text: str) -> str:
    """Forma de comparacao: minusculas, sem acento. O corpus tem
    variantes reais sem acento ('impressao diagnostica', 'lesao'),
    entao casar sem acento evita duplicar cada cue."""
    return strip_accents(text.lower())


# --------------------------------------------------------------------
# Fronteiras de escopo
# --------------------------------------------------------------------
# Marcadores que ENCERRAM o escopo de um cue: pontuacao forte,
# adversativas e verbos de apresentacao que introduzem novo predicado.
# Levantados dos padroes reais do corpus (ver docs/decisions/0012).
_TERMINATION_PATTERNS = [
    r"[.;:]",
    r",",
    r"\bporem\b", r"\bmas\b", r"\bentretanto\b", r"\bcontudo\b", r"\btodavia\b",
    r"\bobservando-se\b", r"\bdestacando-se\b", r"\bevidenciando\b",
    r"\bnotando-se\b", r"\bidentificando-se\b", r"\bassociado a\b",
    r"\bassociada a\b", r"\bassociados a\b", r"\bassociadas a\b",
    r"\bexceto\b", r"\bsalvo\b", r"\bembora\b",
]
_TERMINATION_RE = re.compile("|".join(_TERMINATION_PATTERNS))

# 'e'/'ou' NAO terminam escopo: em 'ligamentos cruzados e colaterais
# integros', a coordenacao compartilha o mesmo predicado. Terminar ali
# quebraria a leitura correta (bug real do vertical anterior).


# --------------------------------------------------------------------
# Cues
# --------------------------------------------------------------------
@dataclass(frozen=True)
class Cue:
    pattern: str
    kind: str        # negation | uncertainty | temporality | comparison | postop
    value: str       # valor canonico atribuido
    direction: str   # forward | backward | bidirectional

    def compiled(self) -> re.Pattern:
        return re.compile(self.pattern)


# Negacao. 'sem' generico entra com fronteira de palavra (nunca casa
# 'sempre'). Cues de negacao no corpus sao dominados por 'sem X' —
# frases compostas ('sem sinais de', 'sem evidencias de') sao apenas
# variantes mais longas do mesmo padrao.
_NEGATION_CUES = [
    Cue(r"\bsem\s+sinais?\s+(?:evidentes?\s+)?d[eo]\b", "negation", "absent", "forward"),
    Cue(r"\bsem\s+evidencias?\s+d[eo]\b", "negation", "absent", "forward"),
    Cue(r"\bsem\s+indicios?\s+d[eo]\b", "negation", "absent", "forward"),
    Cue(r"\bsem\s+", "negation", "absent", "forward"),
    Cue(r"\bnao\s+(?:ha|foram|foi|se\s+observ|se\s+identific|se\s+evidenc|se\s+caracteriz|apresenta|demonstr|visualiz)", "negation", "absent", "forward"),
    Cue(r"\bausencia\s+d[eo]\b", "negation", "absent", "forward"),
    Cue(r"\bausentes?\b", "negation", "absent", "backward"),
    Cue(r"\bnenhum[ao]?\s+", "negation", "absent", "forward"),
    Cue(r"\bnegativ[oa]\s+para\b", "negation", "absent", "forward"),
    Cue(r"\bafastad[oa]s?\b", "negation", "absent", "backward"),
    Cue(r"\bdescartad[oa]s?\b", "negation", "absent", "backward"),
    Cue(r"\bexclui-se\b", "negation", "absent", "forward"),
    Cue(r"\blivres?\s+d[eo]\b", "negation", "absent", "forward"),
    Cue(r"\bisent[oa]s?\s+d[eo]\b", "negation", "absent", "forward"),
]

# Normalidade explicita: NAO e' negacao de um achado especifico, e' a
# afirmacao de que a estrutura esta normal. Fica separada porque o
# significado clinico e' diferente (ver secao 13 do prompt mestre:
# 'ausencia de mencao' != 'normalidade explicita').
_NORMALITY_CUES = [
    Cue(r"\bpreservad[oa]s?\b", "normality", "normal", "backward"),
    Cue(r"\bintegr[oa]s?\b", "normality", "normal", "backward"),
    Cue(r"\bhabitua(?:l|is)\b", "normality", "normal", "backward"),
    Cue(r"\bnormais?\b", "normality", "normal", "backward"),
    Cue(r"\busua(?:l|is)\b", "normality", "normal", "backward"),
    Cue(r"\bconservad[oa]s?\b", "normality", "normal", "backward"),
    Cue(r"\bregulares?\b", "normality", "normal", "backward"),
    Cue(r"\bnormoposicionad[oa]s?\b", "normality", "normal", "backward"),
    Cue(r"\btopic[oa]s?\b", "normality", "normal", "backward"),
]

# Certeza. Ordem importa: o valor mais fraco encontrado prevalece
# (nunca aumentar certeza).
_UNCERTAINTY_CUES = [
    # DUPLA NEGACAO — bug real encontrado ao validar contra o corpus:
    # 'nao podendo ser descartada infiltracao' significa que a
    # infiltracao NAO pode ser excluida (incerteza), mas o cue de
    # negacao 'descartada' sozinho marcava a infiltracao como AUSENTE:
    # inversao completa de polaridade. Estes padroes vem antes e, por
    # serem mais longos, vencem a deduplicacao por containment.
    Cue(r"\bnao\s+(?:se\s+)?pod(?:e|endo|em)\s+ser\s+(?:descartad|afastad|excluid|desconsiderad)[oa]s?\b",
        "uncertainty", "cannot_exclude", "bidirectional"),
    Cue(r"\bnao\s+(?:e|sendo)\s+possivel\s+(?:excluir|afastar|descartar)\b",
        "uncertainty", "cannot_exclude", "bidirectional"),
    Cue(r"\bnao\s+se\s+pode\s+(?:excluir|afastar|descartar)\b", "uncertainty", "cannot_exclude", "bidirectional"),
    Cue(r"\bnao\s+permite\s+(?:excluir|afastar|descartar)\b", "uncertainty", "cannot_exclude", "bidirectional"),
    Cue(r"\bpode\s+(?:corresponder|representar|estar\s+relacionad)", "uncertainty", "possible", "bidirectional"),
    Cue(r"\bpodendo\s+(?:corresponder|representar|relacionar)", "uncertainty", "possible", "bidirectional"),
    Cue(r"\bpossivel(?:mente)?\b", "uncertainty", "possible", "bidirectional"),
    Cue(r"\bsuspeit[ao]\b", "uncertainty", "possible", "bidirectional"),
    Cue(r"\ba\s+esclarecer\b", "uncertainty", "possible", "bidirectional"),
    Cue(r"\bduvidos[ao]\b", "uncertainty", "possible", "bidirectional"),
    Cue(r"\bquestiona-se\b", "uncertainty", "possible", "bidirectional"),
    Cue(r"\bsugestiv[oa]s?\s+d[eo]\b", "uncertainty", "probable", "bidirectional"),
    Cue(r"\bcompativel\s+com\b", "uncertainty", "probable", "bidirectional"),
    Cue(r"\bprovavel(?:mente)?\b", "uncertainty", "probable", "bidirectional"),
    Cue(r"\baparent(?:e|emente)\b", "uncertainty", "probable", "bidirectional"),
    Cue(r"\bdeve\s+corresponder\b", "uncertainty", "probable", "bidirectional"),
]

# Temporalidade / contexto pos-operatorio.
_TEMPORALITY_CUES = [
    Cue(r"\bagud[oa]s?\b", "temporality", "acute", "bidirectional"),
    Cue(r"\bsubagud[oa]s?\b", "temporality", "subacute", "bidirectional"),
    Cue(r"\bcronic[oa]s?\b", "temporality", "chronic", "bidirectional"),
    Cue(r"\bsequela(?:r|res)?\b", "temporality", "sequela", "bidirectional"),
    Cue(r"\bantig[oa]s?\b", "temporality", "chronic", "bidirectional"),
    Cue(r"\bresidua(?:l|is)\b", "temporality", "residual", "bidirectional"),
    Cue(r"\brecente\b", "temporality", "acute", "bidirectional"),
    Cue(r"\bem\s+evolucao\b", "temporality", "evolving", "bidirectional"),
]

_POSTOP_CUES = [
    Cue(r"\bpos-operatori[ao]s?\b", "postop", "postoperative", "bidirectional"),
    Cue(r"\bpos-cirurgic[ao]s?\b", "postop", "postoperative", "bidirectional"),
    Cue(r"\breconstrucao\b", "postop", "postoperative", "bidirectional"),
    Cue(r"\breconstruid[oa]s?\b", "postop", "postoperative", "bidirectional"),
    Cue(r"\benxerto\b", "postop", "graft", "bidirectional"),
    Cue(r"\bmeniscectomia\b", "postop", "postoperative", "bidirectional"),
    Cue(r"\bartrodese\b", "postop", "postoperative", "bidirectional"),
    Cue(r"\bprotese\b", "postop", "implant", "bidirectional"),
    Cue(r"\bmaterial\s+de\s+sintese\b", "postop", "implant", "bidirectional"),
    Cue(r"\bparafus[oa]s?\b", "postop", "implant", "bidirectional"),
    Cue(r"\bplaca\s+metalica\b", "postop", "implant", "bidirectional"),
    Cue(r"\bstent\b", "postop", "implant", "bidirectional"),
    Cue(r"\bcateter\b", "postop", "implant", "bidirectional"),
]

# Comparacao com exame anterior.
_COMPARISON_CUES = [
    Cue(r"\bestave(?:l|is)\b", "comparison", "stable", "bidirectional"),
    Cue(r"\binalterad[oa]s?\b", "comparison", "stable", "bidirectional"),
    Cue(r"\bsem\s+alteracao\s+significativa\s+em\s+relacao\b", "comparison", "stable", "bidirectional"),
    Cue(r"\baumentad[oa]s?\b", "comparison", "increased", "bidirectional"),
    Cue(r"\bmaior\s+que\s+o\s+(?:previo|anterior)\b", "comparison", "increased", "bidirectional"),
    Cue(r"\bem\s+progressao\b", "comparison", "increased", "bidirectional"),
    Cue(r"\bprogressao\b", "comparison", "increased", "bidirectional"),
    Cue(r"\breduzid[oa]s?\b", "comparison", "decreased", "bidirectional"),
    Cue(r"\bmenor\s+que\s+o\s+(?:previo|anterior)\b", "comparison", "decreased", "bidirectional"),
    Cue(r"\bem\s+regressao\b", "comparison", "decreased", "bidirectional"),
    Cue(r"\bregressao\b", "comparison", "decreased", "bidirectional"),
    Cue(r"\bnov[oa]s?\b", "comparison", "new", "bidirectional"),
    Cue(r"\bsurgimento\b", "comparison", "new", "bidirectional"),
    Cue(r"\bresolvid[oa]s?\b", "comparison", "resolved", "bidirectional"),
    Cue(r"\bdesaparecimento\b", "comparison", "resolved", "bidirectional"),
]

# Qualificador etiologico: o achado EXISTE, o que e' incerto e' a
# natureza/causa. Nao e' incerteza sobre a existencia (nao pode virar
# 'possible', que rebaixaria a certeza do proprio achado) nem negacao.
# Levantado do corpus: 'inespecifico' 970x, 'indeterminado' 292x.
_ETIOLOGIC_CUES = [
    Cue(r"\binespecific[oa]s?\b", "etiologic", "nonspecific", "bidirectional"),
    Cue(r"\bindeterminad[oa]s?\b", "etiologic", "indeterminate", "bidirectional"),
    Cue(r"\batipic[oa]s?\b", "etiologic", "atypical", "bidirectional"),
    Cue(r"\bde\s+natureza\s+a\s+esclarecer\b", "etiologic", "indeterminate", "bidirectional"),
]

_ALL_CUES = (_NEGATION_CUES + _NORMALITY_CUES + _UNCERTAINTY_CUES
              + _TEMPORALITY_CUES + _POSTOP_CUES + _COMPARISON_CUES
              + _ETIOLOGIC_CUES)
_COMPILED_CUES = [(c, c.compiled()) for c in _ALL_CUES]


# --------------------------------------------------------------------
# Lateralidade, medidas, graus
# --------------------------------------------------------------------
_LATERALITY_PATTERNS = [
    (re.compile(r"\bbilatera(?:l|is)\b"), "bilateral"),
    (re.compile(r"\bambos\b|\bambas\b"), "bilateral"),
    (re.compile(r"\b(?:a|à)\s+direita\b|\bdireit[oa]s?\b|\bdirei\b"), "right"),
    (re.compile(r"\b(?:a|à)\s+esquerda\b|\besquerd[oa]s?\b"), "left"),
]

# 3,4 x 4,0 x 4,5 cm | 1,2 cm | 9 mm | 0,9 x 0,8 cm
_MEASUREMENT_RE = re.compile(
    r"(\d+(?:[,.]\d+)?)(?:\s*[x×]\s*(\d+(?:[,.]\d+)?))?(?:\s*[x×]\s*(\d+(?:[,.]\d+)?))?"
    r"\s*(cm|mm|ml|cm3|cm³|mm2|mm²|g|ui|mgi)\b"
)

# grau I, grau II/III, grau 2, graus I-II
_GRADE_RE = re.compile(
    r"\bgraus?\s*([ivx]{1,4}|[0-4])(?:\s*[/\-–]\s*([ivx]{1,4}|[0-4]))?\b"
)
_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5"}


@dataclass
class Measurement:
    values: list[float]
    unit: str
    char_start: int
    char_end: int
    raw: str


@dataclass
class CueHit:
    kind: str
    value: str
    direction: str
    char_start: int
    char_end: int
    scope_start: int
    scope_end: int
    raw: str

    def covers(self, start: int, end: int) -> bool:
        """A mencao esta dentro do escopo deste cue?"""
        return start >= self.scope_start and end <= self.scope_end


@dataclass
class Clause:
    text: str
    char_start: int
    char_end: int
    order: int


@dataclass
class ClauseAnalysis:
    """Resultado da analise de UMA sentenca."""
    sentence: str
    sentence_normalized: str
    clauses: list[Clause] = field(default_factory=list)
    cues: list[CueHit] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)
    grades: list[tuple[str, int, int]] = field(default_factory=list)  # (valor, start, end)
    laterality_mentions: list[tuple[str, int, int]] = field(default_factory=list)
    engine_version: str = ENGINE_VERSION

    # ---- consultas por posicao (o coracao do contrato) ----
    def status_at(self, start: int, end: int) -> tuple[str, str | None]:
        """Status da mencao naquela posicao: (status, rule).
        'absent' se coberta por cue de negacao; 'normal' se coberta por
        cue de normalidade; senao 'present'."""
        for cue in self.cues:
            if cue.kind == "negation" and cue.covers(start, end):
                return "absent", cue.raw
        for cue in self.cues:
            if cue.kind == "normality" and cue.covers(start, end):
                return "normal", cue.raw
        return "present", None

    def certainty_at(self, start: int, end: int) -> str:
        """Menor certeza aplicavel (nunca aumenta certeza)."""
        rank = {"cannot_exclude": 0, "possible": 1, "probable": 2, "definite": 3}
        best = "definite"
        for cue in self.cues:
            if cue.kind == "uncertainty" and cue.covers(start, end):
                if rank[cue.value] < rank[best]:
                    best = cue.value
        return best

    def _value_at(self, kind: str, start: int, end: int) -> str | None:
        for cue in self.cues:
            if cue.kind == kind and cue.covers(start, end):
                return cue.value
        return None

    def temporality_at(self, start: int, end: int) -> str | None:
        return self._value_at("temporality", start, end)

    def comparison_at(self, start: int, end: int) -> str | None:
        return self._value_at("comparison", start, end)

    def postop_at(self, start: int, end: int) -> str | None:
        return self._value_at("postop", start, end)

    def etiologic_at(self, start: int, end: int) -> str | None:
        """'inespecifico'/'indeterminado' qualificam a NATUREZA do
        achado, nao a sua existencia — nao rebaixam a certeza."""
        return self._value_at("etiologic", start, end)

    def laterality_at(self, start: int, end: int) -> str | None:
        """Lateralidade LOCAL da frase (o chamador decide como combinar
        com a lateralidade global do exame — sao coisas diferentes)."""
        clause = self.clause_at(start)
        if clause is None:
            return None
        best = None
        best_dist = 10**9
        for value, ms, me in self.laterality_mentions:
            if not (clause.char_start <= ms <= clause.char_end):
                continue
            dist = min(abs(ms - end), abs(start - me))
            if dist < best_dist:
                best, best_dist = value, dist
        return best

    def clause_at(self, pos: int) -> Clause | None:
        for c in self.clauses:
            if c.char_start <= pos <= c.char_end:
                return c
        return None

    def measurements_for(self, start: int, end: int) -> list[Measurement]:
        """Medidas da MESMA clausula, vinculadas por proximidade — evita
        atribuir a medida de um cisto a uma lesao condral citada na
        mesma sentenca (caso adversarial exigido pelo prompt)."""
        clause = self.clause_at(start)
        if clause is None:
            return []
        return [m for m in self.measurements
                if clause.char_start <= m.char_start <= clause.char_end]

    def grades_for(self, start: int, end: int) -> list[str]:
        clause = self.clause_at(start)
        if clause is None:
            return []
        return [g for g, gs, _ge in self.grades
                if clause.char_start <= gs <= clause.char_end]


def _segment_clauses(norm_text: str) -> list[Clause]:
    """Segmenta em clausulas por pontuacao forte. Coordenacao com
    'e'/'ou' NAO abre clausula nova (compartilha predicado)."""
    clauses: list[Clause] = []
    start = 0
    order = 0
    for m in re.finditer(r"[,;:]", norm_text):
        end = m.start()
        chunk = norm_text[start:end]
        if chunk.strip():
            clauses.append(Clause(chunk, start, end, order))
            order += 1
        start = m.end()
    tail = norm_text[start:]
    if tail.strip():
        clauses.append(Clause(tail, start, len(norm_text), order))
    if not clauses:
        clauses = [Clause(norm_text, 0, len(norm_text), 0)]
    return clauses


def _scope_for(norm_text: str, cue: Cue, cue_start: int, cue_end: int) -> tuple[int, int]:
    """Escopo do cue ate o proximo marcador de fronteira, na direcao
    declarada. E' isto que impede a negacao de vazar para outra
    estrutura da mesma sentenca."""
    if cue.direction in ("forward", "bidirectional"):
        term = _TERMINATION_RE.search(norm_text, cue_end)
        fwd_end = term.start() if term else len(norm_text)
    else:
        fwd_end = cue_end

    if cue.direction in ("backward", "bidirectional"):
        bwd_start = 0
        for m in _TERMINATION_RE.finditer(norm_text, 0, cue_start):
            bwd_start = m.end()
    else:
        bwd_start = cue_start

    return bwd_start, fwd_end


# Palavras que nao contam como conteudo proprio ao decidir se uma
# clausula e' "so o qualificador" (regra de aposicao abaixo).
_APPOSITIVE_FILLERS = {
    "de", "do", "da", "dos", "das", "com", "em", "no", "na", "e", "porem",
    "aspecto", "aspectos", "natureza", "carater", "carate", "tipo", "padrao",
    "sendo", "ficando", "mostrando", "se",
}


def _extend_appositive_scopes(analysis: ClauseAnalysis) -> None:
    """Qualificador aposto no fim da frase modifica a clausula anterior.

    'Focos de alteração de sinal na substância branca, inespecíficos.'
    — o qualificador vem depois da virgula, entao o escopo para tras
    (que termina na virgula, por seguranca contra vazamento de negacao)
    nao alcancaria o achado que ele qualifica.

    A regra e' deliberadamente estreita: so vale quando a clausula do
    cue nao tem conteudo proprio alem do proprio qualificador. Assim
    'X, sem Y' (que tem 'Y' como conteudo) NAO estende — que e'
    exatamente o caso onde estender inverteria a polaridade de X."""
    by_order = {c.order: c for c in analysis.clauses}
    for cue in analysis.cues:
        if cue.direction not in ("backward", "bidirectional"):
            continue
        clause = analysis.clause_at(cue.char_start)
        if clause is None or clause.order == 0:
            continue
        rel_start = cue.char_start - clause.char_start
        rel_end = cue.char_end - clause.char_start
        remainder = clause.text[:rel_start] + clause.text[rel_end:]
        tokens = [t for t in re.findall(r"\w+", remainder) if t not in _APPOSITIVE_FILLERS]
        if len(tokens) > 1:
            continue
        prev = by_order.get(clause.order - 1)
        if prev is not None:
            cue.scope_start = min(cue.scope_start, prev.char_start)


def _dedupe_contained(hits: list[CueHit]) -> list[CueHit]:
    """Descarta cue cujo span esta CONTIDO no span de outro cue.

    Duas correcoes reais de uma vez:
      - 'nao e possivel excluir X' disparava tambem 'possivel'
        (uncertainty=possible), competindo com cannot_exclude;
      - 'nao podendo ser descartada X' disparava o cue de negacao
        'descartada', invertendo a polaridade do achado.
    O match MAIS LONGO e' a leitura mais especifica e vence. Sobreposicao
    parcial (sem containment) e' preservada: sao cues distintos."""
    ordered = sorted(hits, key=lambda h: (-(h.char_end - h.char_start), h.char_start))
    kept: list[CueHit] = []
    for hit in ordered:
        contained = any(
            k.char_start <= hit.char_start and hit.char_end <= k.char_end
            and not (k.char_start == hit.char_start and k.char_end == hit.char_end)
            for k in kept
        )
        if not contained:
            kept.append(hit)
    return sorted(kept, key=lambda h: h.char_start)


def analyze_sentence(sentence: str) -> ClauseAnalysis:
    """Analisa UMA sentenca. Trabalha sobre a forma sem acento para
    casar as variantes reais do corpus, mas preserva os offsets — a
    normalizacao usada e' 1:1 em caracteres (apenas remove diacriticos
    e baixa a caixa), entao os indices valem tambem no texto original."""
    norm = _norm(sentence)
    analysis = ClauseAnalysis(sentence=sentence, sentence_normalized=norm)
    analysis.clauses = _segment_clauses(norm)

    raw_hits: list[CueHit] = []
    for cue, pattern in _COMPILED_CUES:
        for m in pattern.finditer(norm):
            scope_start, scope_end = _scope_for(norm, cue, m.start(), m.end())
            raw_hits.append(CueHit(
                kind=cue.kind, value=cue.value, direction=cue.direction,
                char_start=m.start(), char_end=m.end(),
                scope_start=scope_start, scope_end=scope_end,
                raw=sentence[m.start():m.end()],
            ))
    analysis.cues = _dedupe_contained(raw_hits)
    _extend_appositive_scopes(analysis)

    for m in _MEASUREMENT_RE.finditer(norm):
        values = [float(g.replace(",", ".")) for g in m.groups()[:3] if g]
        analysis.measurements.append(Measurement(
            values=values, unit=m.group(4), char_start=m.start(),
            char_end=m.end(), raw=sentence[m.start():m.end()],
        ))

    for m in _GRADE_RE.finditer(norm):
        g1 = _ROMAN.get(m.group(1), m.group(1))
        g2 = _ROMAN.get(m.group(2), m.group(2)) if m.group(2) else None
        analysis.grades.append((f"{g1}_{g2}" if g2 else g1, m.start(), m.end()))

    for pattern, value in _LATERALITY_PATTERNS:
        for m in pattern.finditer(norm):
            analysis.laterality_mentions.append((value, m.start(), m.end()))

    return analysis
