"""Section parser GLOBAL — todas as modalidades e tipos de exame.

Origem dos cabecalhos: levantados empiricamente sobre os 8.402 laudos
do corpus completo (RM/TC/RX), nao assumidos. Ver
data/derived/qa/_header_mining.json (fora do git — contem trechos de
texto real) e CLINICAL_QA_REPORT.json para as contagens agregadas.

Historico: a versao anterior deste modulo foi calibrada apenas nos 911
laudos de RM de joelho. Medida sobre o corpus inteiro, ela deixava
39,2% dos RM, 48,2% dos TC e 95,3% dos RX com cabecalho nao
reconhecido — e, pior, 96,2% dos RX SEM nenhuma secao de achados,
porque um cabecalho desconhecido reclassificava todo o resto do laudo
como 'other'. Ver ADR 0011.

Tres mudancas de desenho corrigem isso:

1. Cabecalho desconhecido NAO troca mais o tipo da secao. Ele vira uma
   SUBSECAO rotulada da secao corrente (section_subtype). Assim o
   conteudo nunca muda de classificacao por causa de um rotulo que o
   parser nao conhece — o pior caso passa a ser 'rotulo desconhecido',
   nunca 'achados viraram outro'.
2. Bloco de titulo (linhas de modalidade/anatomia no inicio do laudo)
   e' reconhecido genericamente, por posicao + forma, em vez de uma
   lista fixa de titulos de joelho.
3. Achados implicitos: laudos de RX tipicamente nao usam 'RELATÓRIO:'.
   Eles abrem os achados com uma frase-guia ('As radiografias digitais
   ... mostram:'). Essa frase abre uma secao de achados marcada como
   implicita (section_subtype='implicit_lead_in'), com rastreabilidade
   — nunca e' apresentada como se houvesse cabecalho explicito.

Tipos de secao (ESPECIFICACAO_MESTRA secao 12):
indication, technique, comparison, findings, impression, recommendation, other
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Palavras de titulo de exame (linha de modalidade). Prefixo, casefold.
_MODALITY_TITLE_PREFIXES = (
    "ressonância", "ressonancia", "angiorressonância", "angiorressonancia",
    "tomografia", "angiotomografia", "tomografia computadorizda",  # typo real
    "radiografia", "telerradiografia", "densitometria", "mamografia",
    "ultrassonografia", "ultrassom", "escanometria", "angiotc",
    "folha de leitura", "laudo",
)

# Linhas de tag/metadado (codigo CID/ICD-10, com variantes de digitacao
# observadas: CDI, CIS) que aparecem soltas DENTRO de uma secao e NAO
# devem abrir uma nova secao — sao conteudo da secao corrente.
_TAG_LINE_RE = re.compile(r"^(CID|CDI|CIS)\b", re.IGNORECASE)

# (prefixo apos casefold, tipo). Usa startswith para cobrir variantes
# com CID embutido no cabecalho ou data no caso de comparacao.
# Ordem importa: prefixos mais especificos primeiro.
_HEADER_PREFIXES: list[tuple[str, str]] = [
    # --- indicacao ---
    ("informações clínicas", "indication"),
    ("informações sobre o exame", "indication"),
    ("indicação clínica", "indication"),
    ("indicação clinica", "indication"),   # sem acento, real no corpus
    ("indicação", "indication"),
    ("antecedentes", "indication"),
    ("história clínica", "indication"),
    ("dados clínicos", "indication"),
    # --- tecnica ---
    ("técnica de exame", "technique"),
    ("técnica do exame", "technique"),
    ("técnica", "technique"),
    ("tecnica", "technique"),
    ("protocolo", "technique"),
    # --- comparacao ---
    ("análise comparativa", "comparison"),
    ("estudo comparativo", "comparison"),
    ("exames anteriores", "comparison"),
    ("exame anterior", "comparison"),
    ("comparativo", "comparison"),
    ("este estudo foi correlacionado com", "comparison"),
    ("atual anterior", "comparison"),
    ("anterior", "comparison"),
    ("atual", "comparison"),
    # --- achados ---
    ("relatório", "findings"),
    ("relatorio", "findings"),             # sem acento, real no corpus
    ("os seguintes aspectos foram observados", "findings"),
    ("análise", "findings"),               # confirmado por contexto: abre descricao anatomica
    ("achados adicionais", "findings"),
    ("achado adicional", "findings"),
    ("achados", "findings"),
    # --- impressao ---
    ("impressão diagnóstica", "impression"),
    ("impressão diagnostica", "impression"),   # sem acento, 1.139x no corpus
    ("imressão diagnóstica", "impression"),    # typo real observado (CAIO)
    ("impressão", "impression"),
    ("conclusão", "impression"),
    ("opinião", "impression"),
    ("opiniao", "impression"),
    # --- recomendacao ---
    ("recomendação", "recommendation"),
    ("recomendações", "recommendation"),
    ("sugere-se", "recommendation"),
    ("sugestão", "recommendation"),
]

# Subsecoes de ACHADOS conhecidas: nao trocam o tipo de secao, apenas
# rotulam. Levantadas do corpus (frequencia >= 20).
_KNOWN_FINDINGS_SUBSECTIONS = {
    "medidas", "níveis discais", "niveis discais", "escore de cálcio",
    "anormalidades de parênquima", "mapeamento dos miomas",
    "áreas sugeridas para biópsia", "análise prostática & uretral morfoestrutural",
    "demais achados do estudo neurográfico", "valores de referência",
    "referência", "referência classificação figo", "comentário",
    "dimensões (cm)", "volume (cm³)",
}

# Frase-guia que abre achados sem cabecalho explicito (padrao dominante
# em RX). Termina em ':' e usa verbo de apresentacao. Levantada do
# corpus: 'As radiografias digitais ... mostram:', 'As telerradiografias
# do tórax em PA e perfil mostram:', 'Controle evolutivo tomografico,
# evidenciando:', '..., destacando-se:'.
_FINDINGS_LEAD_IN_RE = re.compile(
    r"(mostra|mostram|evidencia|evidenciam|evidenciando|revela|revelam|"
    r"demonstra|demonstram|destacando-se|observando-se|apresenta|apresentam)\s*:\s*$",
    re.IGNORECASE,
)


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


def _is_modality_title(line: str) -> bool:
    key = line.casefold().rstrip(":").strip()
    return any(key.startswith(p) for p in _MODALITY_TITLE_PREFIXES)


def _classify_header(line: str) -> str | None:
    """Retorna section_type conhecido, ou None se o rotulo nao e'
    reconhecido (o chamador decide o que fazer — nunca adivinha)."""
    key = line.casefold().rstrip(":").strip()
    for prefix, section_type in _HEADER_PREFIXES:
        if key.startswith(prefix):
            return section_type
    return None


def _is_known_findings_subsection(line: str) -> bool:
    return line.casefold().rstrip(":").strip() in _KNOWN_FINDINGS_SUBSECTIONS


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
    # Rotulo adicional preservado sem alterar o tipo da secao:
    # 'exam_title', 'implicit_lead_in', 'subsection:<rotulo>'.
    section_subtype: str | None = None


@dataclass
class SectionParseResult:
    sections: list[ParsedSection] = field(default_factory=list)
    unmatched_header_candidates: list[str] = field(default_factory=list)

    def has_type(self, section_type: str) -> bool:
        return any(s.section_type == section_type for s in self.sections)


_CLINICAL_TYPES = {"indication", "technique", "comparison", "findings",
                    "impression", "recommendation"}


def parse_sections(clean_text: str) -> SectionParseResult:
    lines = clean_text.split("\n")
    result = SectionParseResult()

    current_type = "other"
    current_header: str | None = None
    current_subtype: str | None = None
    current_buffer: list[str] = []
    order = 0
    seen_clinical_section = False

    def flush():
        nonlocal order
        text = "\n".join(current_buffer).strip("\n")
        if text.strip():
            result.sections.append(ParsedSection(
                section_type=current_type,
                section_order=order,
                text_raw=text,
                header_line=current_header,
                unmatched_header=(current_subtype or "").startswith("unknown_subsection:"),
                section_subtype=current_subtype,
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
            current_subtype = None
            seen_clinical_section = True
            current_buffer = [remainder] if remainder else []
            continue

        # Frase-guia de achados implicitos (padrao dominante em RX, que
        # nao usa 'RELATÓRIO:'). A propria frase-guia fica no corpo da
        # secao — ela e' conteudo, nao rotulo.
        if _FINDINGS_LEAD_IN_RE.search(line) and not _looks_like_header(line):
            if current_type != "findings":
                flush()
                current_type = "findings"
                current_header = None
                current_subtype = "implicit_lead_in"
                seen_clinical_section = True
                current_buffer = [raw_line]
                continue

        if _looks_like_header(line):
            section_type = _classify_header(line)

            if section_type is not None:
                flush()
                current_type = section_type
                current_header = line
                current_subtype = None
                seen_clinical_section = True
                current_buffer = []
                continue

            # Cabecalho NAO reconhecido.
            if not seen_clinical_section:
                # Antes de qualquer secao clinica: bloco de titulo
                # (modalidade/anatomia). Nao e' anomalia estrutural.
                flush()
                current_type = "other"
                current_header = line
                current_subtype = "exam_title_modality" if _is_modality_title(line) else "exam_title_anatomy"
                current_buffer = []
                continue

            # Dentro de uma secao clinica: vira SUBSECAO rotulada, sem
            # trocar o tipo — o conteudo continua pertencendo a secao
            # corrente (achados continuam achados). E' esta regra que
            # corrige a perda de 96% dos achados em RX.
            flush()
            current_header = line
            if _is_known_findings_subsection(line):
                current_subtype = f"subsection:{line}"
            else:
                result.unmatched_header_candidates.append(line)
                current_subtype = f"unknown_subsection:{line}"
            current_buffer = []
            continue

        current_buffer.append(raw_line)

    flush()

    # Ultimo recurso: laudo sem NENHUMA secao de achados reconhecida,
    # mas com corpo substantivo em 'other' depois do bloco de titulo.
    # Promove esse corpo a achados, marcado como implicito — melhor
    # sinalizar 'achados inferidos por posicao' do que descartar o
    # conteudo clinico do laudo inteiro.
    if not result.has_type("findings"):
        for section in result.sections:
            if section.section_type != "other":
                continue
            if (section.section_subtype or "").startswith("exam_title") and len(section.text_raw.split()) <= 8:
                continue
            if len(section.text_raw.split()) >= 12:
                section.section_type = "findings"
                section.section_subtype = "implicit_no_header"

    return result
