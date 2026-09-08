"""Banco de frases derivado do corpus real (nao de LLM, nao inventado).

Para cada combinacao (estrutura, achado, status, gravidade, localizacao,
secao), agrega as frases REAIS (sentences.text_raw) que a Fase 4 ja
ligou a essa combinacao via clinical_concepts, com contagem de
frequencia e medico de origem. O Report Compiler usa isto para redigir
achados usando linguagem real de laudo, nunca prosa gerada livremente.

Isto e uma versao minima da 'biblioteca de frases' da Fase 3 —
implementada aqui apenas com o que o Report Compiler precisa
(rastreada ate a frase real de qual medico, por ESPECIFICACAO_MESTRA
secao 31), nao a biblioteca completa e generica da especificacao.

LIMITACAO RECONHECIDA (ver docs/decisions/0006): uma frase real do
corpus pode conter conteudo clinico ALEM do que o conceito extraido
capturou (ex.: 'Degeneração difusa do menisco lateral, sem roturas.'
foi extraida como apenas 'menisco lateral, tear ausente' — a
degeneracao nao virou nenhum conceito porque, PARA ESSA ESTRUTURA, o
extrator so emite um achado por sentenca). Reusar essa frase para
outro paciente que nao tem degeneracao seria uma inconsistencia. Como
mitigacao parcial, o banco PREFERE frases 'limpas' — sentencas que
produziram exatamente 1 conceito no total (nao apenas 1 por estrutura)
— sobre frases 'compostas' (a mesma sentenca gerou 2+ conceitos,
sinal de que ela describe mais de uma coisa). Isso reduz mas NAO
elimina o risco: uma sentenca pode ser 'limpa' pela contagem de
conceitos e ainda conter prosa nao capturada por nenhuma regra (recall
da Fase 4 e ~57%, nao 100%). Por isso todo laudo compilado por esta
camada deve ser revisado pelo medico antes do uso — nao e' uma
sugestao de estilo, e uma limitacao estrutural desta fase.
"""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

# chave: (structure, finding, status, severity, location, section_type)
PhraseKey = tuple[str, str, str, str | None, str | None, str]


@dataclass
class PhraseCandidate:
    text: str
    doctor: str
    frequency: int
    clean: bool  # True: a sentenca de origem produziu so este 1 conceito


class PhraseBank:
    def __init__(self):
        # key -> {True: Counter[(doctor,text)] (limpa), False: Counter (composta)}
        self._by_key: dict[PhraseKey, dict[bool, Counter]] = defaultdict(
            lambda: {True: Counter(), False: Counter()}
        )

    def add(self, key: PhraseKey, doctor: str, text: str, clean: bool) -> None:
        self._by_key[key][clean][(doctor, text)] += 1

    def lookup(self, key: PhraseKey, preferred_doctor: str | None = None) -> PhraseCandidate | None:
        """Prioriza frases 'limpas' (sentenca de origem com 1 unico
        conceito) sobre 'compostas'. Dentro de cada grupo, prioriza a
        mais frequente do preferred_doctor; sem isso, a mais frequente
        geral. Nunca inventa uma frase — so escolhe entre as reais."""
        buckets = self._by_key.get(key)
        if not buckets:
            return None
        for clean in (True, False):
            counter = buckets[clean]
            if not counter:
                continue
            if preferred_doctor:
                doctor_items = [(dt, c) for dt, c in counter.items() if dt[0] == preferred_doctor]
                if doctor_items:
                    (doctor, text), freq = max(doctor_items, key=lambda kv: kv[1])
                    return PhraseCandidate(text=text, doctor=doctor, frequency=freq, clean=clean)
            (doctor, text), freq = counter.most_common(1)[0]
            return PhraseCandidate(text=text, doctor=doctor, frequency=freq, clean=clean)
        return None

    def lookup_relaxed(
        self, structure: str, finding: str, status: str,
        severity: str | None, location: str | None, section_type: str,
        preferred_doctor: str | None = None,
    ) -> tuple[PhraseCandidate | None, PhraseKey | None]:
        """Tenta a chave exata; se nao houver frase real, relaxa
        primeiro a localizacao, depois a gravidade — NUNCA relaxa
        structure/finding/status (isso mudaria o que esta sendo dito).
        Retorna (candidato_ou_None, chave_que_bateu_ou_None)."""
        candidates_keys = [
            (structure, finding, status, severity, location, section_type),
            (structure, finding, status, severity, None, section_type),
            (structure, finding, status, None, None, section_type),
        ]
        seen = set()
        for key in candidates_keys:
            if key in seen:
                continue
            seen.add(key)
            result = self.lookup(key, preferred_doctor)
            if result:
                return result, key
        return None, None

    def entries(self) -> list[dict]:
        """Enumera todas as combinacoes conhecidas — usado pela API
        para alimentar a biblioteca de achados pesquisavel. Cada
        entrada traz a frase mais representativa (via lookup) e
        metadados agregados (frequencia total, medicos que a usaram)."""
        out = []
        for key, buckets in self._by_key.items():
            combined = buckets[True] + buckets[False]
            if not combined:
                continue
            total_freq = sum(combined.values())
            doctors = sorted({doctor for doctor, _text in combined})
            example = self.lookup(key)
            structure, finding, status, severity, location, section_type = key
            out.append({
                "structure": structure, "finding": finding, "status": status,
                "severity": severity, "location": location, "section_type": section_type,
                "example_text": example.text if example else "",
                "frequency": total_freq, "doctors": doctors,
            })
        return out


def build_phrase_bank(conn: sqlite3.Connection) -> PhraseBank:
    bank = PhraseBank()

    concept_count_by_sentence = dict(conn.execute(
        "SELECT sentence_id, COUNT(*) FROM clinical_concepts GROUP BY sentence_id"
    ).fetchall())

    rows = conn.execute(
        """
        SELECT cc.sentence_id, cc.structure, cc.finding, cc.status, cc.severity,
               cc.location, cc.section_type, cc.doctor, s.text_raw
        FROM clinical_concepts cc
        JOIN sentences s ON cc.sentence_id = s.id
        """
    ).fetchall()
    for sentence_id, structure, finding, status, severity, location, section_type, doctor, text in rows:
        key = (structure, finding, status, severity, location, section_type)
        is_clean = concept_count_by_sentence.get(sentence_id, 1) == 1
        bank.add(key, doctor, text, clean=is_clean)
    return bank
