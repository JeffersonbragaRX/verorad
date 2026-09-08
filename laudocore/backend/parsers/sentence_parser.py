"""Sentence parser: quebra o texto de uma secao em unidades clinicas.

No corpus observado (RM de joelho), cada linha ja tende a ser uma
unidade clinica isolada (um achado por linha). Ainda assim, algumas
linhas contem mais de uma frase separada por ponto final. O split usa
pontuacao de fim de frase seguida de espaco + maiuscula/digito/marcador
de lista ('#'), o que evita quebrar em abreviacoes comuns do texto
(ex.: 'T1', 'T2', '3T') porque essas nao sao seguidas de espaco+maiuscula
dentro da mesma frase.
"""

from __future__ import annotations

import re

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ0-9#])")


def split_sentences(section_text: str) -> list[str]:
    sentences: list[str] = []
    for raw_line in section_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        for piece in _SENTENCE_SPLIT_RE.split(line):
            piece = piece.strip()
            if piece:
                sentences.append(piece)
    return sentences
