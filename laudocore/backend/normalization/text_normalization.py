"""Normalizacao nao destrutiva do texto do laudo (RAW -> clean -> normalized).

Regra do projeto (ESPECIFICACAO_MESTRA secao 9): sempre manter as tres
versoes: raw (intocado), clean (limpeza segura, exibivel), normalized
(apenas para comparacao/hash, nunca exibido como laudo final).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_INVISIBLE_CHARS = (
    "​"  # zero width space
    "‌"  # zero width non-joiner
    "‍"  # zero width joiner
    "﻿"  # BOM
)
_INVISIBLE_RE = re.compile("[" + _INVISIBLE_CHARS + "]")
_TRAILING_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")
_WHITESPACE_RUN_RE = re.compile(r"\s+")


def clean(raw_text: str) -> str:
    """Limpeza segura: Unicode, caracteres invisiveis, espacos finais,
    quebras excessivas. Nunca remove ou reescreve conteudo clinico."""
    text = unicodedata.normalize("NFC", raw_text)
    text = _INVISIBLE_RE.sub("", text)
    text = _TRAILING_WS_RE.sub("", text)
    text = _EXCESS_BLANK_LINES_RE.sub("\n\n", text)
    return text.strip("\n")


def normalized(clean_text: str) -> str:
    """Apenas para comparacao/hash — NUNCA usar como laudo final."""
    text = clean_text.casefold()
    text = _WHITESPACE_RUN_RE.sub(" ", text)
    return text.strip()


def exact_hash(clean_text: str) -> str:
    return hashlib.sha256(clean_text.encode("utf-8")).hexdigest()


def normalized_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
