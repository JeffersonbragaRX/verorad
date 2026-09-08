"""Section parser para RM de joelho (vertical piloto da Fase 1).

Os cabecalhos abaixo NAO foram assumidos: foram levantados
empiricamente a partir dos 911 laudos reais de RM_JOELHO_D/RM_JOELHO_E
(ver docs/data_dictionary.md, secao "Cabecalhos observados por medico").
Cada medico usa um conjunto proprio de cabecalhos — nao ha estrutura
unica. Um cabecalho que nao aparece nesta lista NAO e' classificado por
adivinhacao: vira uma secao do tipo "other" e e' registrado como
"unmatched_header_candidate" no QA report, para revisao humana.

Tipos de secao (ESPECIFICACAO_MESTRA secao 12):
indication, technique, comparison, findings, impression, recommendation, other
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Linhas de titulo/equipamento conhecidas — nao sao secoes clinicas,
# viram "other" com subtype "exam_title" sem gerar alerta de anomalia.
_KNOWN_TITLE_LINES = {
    "RESSONÂNCIA MAGNÉTICA",
    "RESSONÂNCIA MAGNÉTICA BIOMATRIX",
    "RESSONÂNCIA MAGNÉTICA 3T BIOMATRIX",
    "RESSONÂNCIA MAGNÉTICA 3T MULTIPARAMÉTRICA BIOMATRIX",
    "RESSONÂNCIA MAGNÉTICA JOELHO DIREITO",
    "RESSONÂNCIA MAGNÉTICA JOELHO ESQUERDO",
    "JOELHO DIREITO",
    "JOELHO ESQUERDO",
}

# Linhas de tag/metadado (codigo CID/ICD-10, com variantes de digitacao
# observadas: CDI, CIS) que aparecem soltas DENTRO de uma secao (em
# geral logo apos 'INDICAÇÃO CLÍNICA:'/'INFORMAÇÕES CLÍNICAS:') e NÃO
# devem abrir uma nova secao — sao conteudo da secao corrente. Sem este
# tratamento, a heuristica de deteccao de cabecalho (linha curta,
# maiuscula) as confundia com cabecalhos desconhecidos e as arrancava
# do corpo da indicacao clinica.
_TAG_LINE_RE = re.compile(r"^(CID|CDI|CIS)\b", re.IGNORECASE)

# (prefixo apos casefold, tipo). Usa startswith para cobrir variantes
# com CID embutido no cabecalho ou data no caso de comparacao.
_HEADER_PREFIXES: list[tuple[str, str]] = [
    ("informações clínicas", "indication"),
    ("indicação clínica", "indication"),
    ("técnica de exame", "technique"),
    ("técnica", "technique"),
    ("relatório", "findings"),
    ("os seguintes aspectos foram observados", "findings"),
    ("impressão diagnóstica", "impression"),
    ("imressão diagnóstica", "impression"),  # typo real observado (CAIO, 1x)
    ("análise comparativa", "comparison"),
    ("estudo comparativo", "comparison"),
    ("anterior", "comparison"),
    ("atual", "comparison"),
]


def _looks_like_header(line: str) -> bool:
    """Heuristica usada tambem na descoberta empirica dos cabecalhos:
    linha curta, sem pontuacao de frase, tipicamente maiuscula ou
    terminada em ':'. Sentencas clinicas normais no corpus nao sao
    escritas em caixa alta nem tao curtas, entao o risco de falso
    positivo dentro do corpo do laudo e baixo."""
    if not line:
        return False
    letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", line)
    if not letters:
        return False
    is_all_caps = letters.upper() == letters
    is_short_or_colon = line.endswith(":") or len(line.split()) <= 5
    return bool(is_all_caps and is_short_or_colon and len(line) <= 60)


def _classify_header(line: str) -> tuple[str | None, bool]:
    """Retorna (section_type, is_title). section_type None = cabecalho
    nao reconhecido (vira 'other' + alerta)."""
    stripped = line.rstrip(":").strip()
    if stripped in _KNOWN_TITLE_LINES:
        return "other", True
    key = line.casefold().rstrip(":").strip()
    for prefix, section_type in _HEADER_PREFIXES:
        if key.startswith(prefix):
            return section_type, False
    return None, False


# Compilados uma vez: alguns medicos (CAIO, RAFAEL) escrevem
# 'CABECALHO: conteudo' na MESMA linha, em vez de cabecalho isolado
# seguido de conteudo nas linhas seguintes (padrao de NEY/SAMIR). Sem
# isso, achados descobertos empiricamente mostraram 0% de cobertura de
# 'technique' para CAIO — nao porque a informacao esta ausente, mas
# porque o parser so reconhecia cabecalho em linha propria.
_INLINE_HEADER_PATTERNS = [
    (re.compile(r"^(" + re.escape(prefix) + r"\s*:)\s*(.*)$", re.IGNORECASE), section_type)
    for prefix, section_type in _HEADER_PREFIXES
]


def _match_inline_header(line: str) -> tuple[str, str, str] | None:
    """Casa 'PREFIXO: resto' em uma unica linha. Retorna
    (section_type, header_label, remainder) ou None."""
    for pattern, section_type in _INLINE_HEADER_PATTERNS:
        m = pattern.match(line)
        if m:
            return section_type, m.group(1), m.group(2).strip()
    return None


@dataclass
class ParsedSection:
    section_type: str
    section_order: int
    text_raw: str
    header_line: str | None
    unmatched_header: bool = False


@dataclass
class SectionParseResult:
    sections: list[ParsedSection] = field(default_factory=list)
    unmatched_header_candidates: list[str] = field(default_factory=list)

    def has_type(self, section_type: str) -> bool:
        return any(s.section_type == section_type for s in self.sections)


def parse_sections(clean_text: str) -> SectionParseResult:
    lines = clean_text.split("\n")
    result = SectionParseResult()

    current_type = "other"
    current_header: str | None = None
    current_buffer: list[str] = []
    order = 0

    def flush():
        nonlocal order
        text = "\n".join(current_buffer).strip("\n")
        if text.strip():
            result.sections.append(ParsedSection(
                section_type=current_type,
                section_order=order,
                text_raw=text,
                header_line=current_header,
                unmatched_header=(current_header is not None and current_type == "other"
                                   and current_header not in _KNOWN_TITLE_LINES),
            ))
            order += 1

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            current_buffer.append(raw_line)
            continue

        if _TAG_LINE_RE.match(line):
            current_buffer.append(raw_line)
            continue

        inline_match = _match_inline_header(line)
        if inline_match is not None:
            section_type, header_label, remainder = inline_match
            flush()
            current_type = section_type
            current_header = header_label
            current_buffer = [remainder] if remainder else []
            continue

        if _looks_like_header(line):
            section_type, _is_title = _classify_header(line)
            if section_type is None:
                result.unmatched_header_candidates.append(line)
                section_type = "other"
            # fecha a secao anterior (se houver conteudo) e abre uma nova,
            # inclusive para linhas de titulo (cada uma vira um bloco
            # "other" curto — sem impacto no parsing clinico downstream).
            flush()
            current_type = section_type
            current_header = line
            current_buffer = []
            continue

        current_buffer.append(raw_line)

    flush()
    return result
