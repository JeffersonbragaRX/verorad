"""Banco de frases derivado do corpus real (nao de LLM, nao inventado).

Para cada combinacao (estrutura, achado, status, gravidade, localizacao,
secao), agrega as frases REAIS (sentences.text_raw) que a Fase 4 ja
ligou a essa combinacao via clinical_concepts, com contagem de
frequencia, medico e lateralidade de origem. O Report Compiler usa isto
para redigir achados usando linguagem real de laudo, nunca prosa gerada
livremente.

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
da Fase 4 e ~58%, nao 100%). Por isso todo laudo compilado por esta
camada deve ser revisado pelo medico antes do uso — nao e' uma
sugestao de estilo, e uma limitacao estrutural desta fase.
"""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

# chave: (structure, finding, status, severity, location, section_type)
PhraseKey = tuple[str, str, str, str | None, str | None, str]

# Palavras que denunciam que a frase nomeia um LADO explicitamente —
# usadas para nao reaproveitar, sem aviso, uma frase de um joelho D
# num laudo de joelho E (ou vice-versa). Ver PhraseBank._mentions_side.
_SIDE_WORDS = {"D": ["direito", "direita"], "E": ["esquerdo", "esquerda"]}


@dataclass
class _PhraseEntry:
    doctor: str
    text: str
    laterality: str | None  # 'D' | 'E' | None (desconhecida)
    clean: bool  # True: a sentenca de origem produziu so este 1 conceito


@dataclass
class PhraseCandidate:
    text: str
    doctor: str
    frequency: int
    clean: bool  # True: a sentenca de origem produziu so este 1 conceito
    mismatched_laterality: bool = False  # True: frase de exame do lado oposto e nomeia o lado
    mismatched_doctor: bool = False  # True: nenhuma frase do medico preferido existia p/ esta chave


class PhraseBank:
    def __init__(self):
        self._by_key: dict[PhraseKey, list[_PhraseEntry]] = defaultdict(list)

    def add(self, key: PhraseKey, doctor: str, text: str, clean: bool,
            laterality: str | None = None) -> None:
        self._by_key[key].append(_PhraseEntry(doctor=doctor, text=text,
                                               laterality=laterality, clean=clean))

    @staticmethod
    def _mentions_opposite_side(entry: _PhraseEntry, preferred_laterality: str | None) -> bool:
        """True quando a frase vem de um exame do lado OPOSTO ao pedido
        e o proprio texto nomeia um lado explicitamente ('joelho
        direito'/'joelho esquerdo') — risco real de o laudo compilado
        afirmar o lado errado. Frases sem mencao de lado nao entram
        aqui (a maioria — 'menisco lateral' e compartimento anatomico,
        nao lateralidade do joelho)."""
        if preferred_laterality is None or entry.laterality is None:
            return False
        if entry.laterality == preferred_laterality:
            return False
        opposite_words = _SIDE_WORDS.get(entry.laterality, [])
        text_lower = entry.text.lower()
        return any(w in text_lower for w in opposite_words)

    def lookup(
        self, key: PhraseKey, preferred_doctor: str | None = None,
        preferred_laterality: str | None = None,
    ) -> PhraseCandidate | None:
        """Prioriza, nesta ordem: (1) frases 'limpas' sobre 'compostas';
        (2) dentro de cada grupo, do medico preferido E sem risco de
        lateralidade; (3) sem risco de lateralidade (qualquer medico);
        (4) so entao, como ultimo recurso, qualquer frase disponivel —
        marcando o candidato com mismatched_laterality/mismatched_doctor
        para o chamador decidir o que fazer (nunca decide sozinho por
        omissao). Nunca inventa uma frase — so escolhe entre as reais."""
        entries = self._by_key.get(key)
        if not entries:
            return None
        for clean in (True, False):
            bucket = [e for e in entries if e.clean == clean]
            if bucket:
                candidate = self._pick(bucket, preferred_doctor, preferred_laterality)
                if candidate:
                    return candidate
        return None

    def _pick(
        self, bucket: list[_PhraseEntry], preferred_doctor: str | None,
        preferred_laterality: str | None,
    ) -> PhraseCandidate | None:
        safe = [e for e in bucket if not self._mentions_opposite_side(e, preferred_laterality)]

        if preferred_doctor:
            safe_preferred_doctor = [e for e in safe if e.doctor == preferred_doctor]
            if safe_preferred_doctor:
                return self._most_common(safe_preferred_doctor, mismatched_laterality=False,
                                          mismatched_doctor=False)
        if safe:
            return self._most_common(safe, mismatched_laterality=False,
                                      mismatched_doctor=bool(preferred_doctor))

        # Nada seguro disponivel (todas as frases da chave nomeiam o
        # lado oposto): usa mesmo assim, mas o candidato sai marcado —
        # o chamador (Report Compiler) converte isso num aviso
        # bloqueante em vez de compilar em silencio.
        if preferred_doctor:
            doctor_entries = [e for e in bucket if e.doctor == preferred_doctor]
            if doctor_entries:
                return self._most_common(doctor_entries, mismatched_laterality=True,
                                          mismatched_doctor=False)
        return self._most_common(bucket, mismatched_laterality=True,
                                  mismatched_doctor=bool(preferred_doctor))

    @staticmethod
    def _most_common(
        entries: list[_PhraseEntry], mismatched_laterality: bool, mismatched_doctor: bool,
    ) -> PhraseCandidate:
        counter = Counter((e.doctor, e.text) for e in entries)
        (doctor, text), freq = counter.most_common(1)[0]
        return PhraseCandidate(
            text=text, doctor=doctor, frequency=freq, clean=entries[0].clean,
            mismatched_laterality=mismatched_laterality, mismatched_doctor=mismatched_doctor,
        )

    def lookup_relaxed(
        self, structure: str, finding: str, status: str,
        severity: str | None, location: str | None, section_type: str,
        preferred_doctor: str | None = None, preferred_laterality: str | None = None,
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
            result = self.lookup(key, preferred_doctor, preferred_laterality)
            if result:
                return result, key
        return None, None

    def entries(self) -> list[dict]:
        """Enumera todas as combinacoes conhecidas — usado pela API
        para alimentar a biblioteca de achados pesquisavel. Cada
        entrada traz a frase mais representativa (via lookup) e
        metadados agregados (frequencia total, medicos que a usaram)."""
        out = []
        for key, entries in self._by_key.items():
            if not entries:
                continue
            total_freq = len(entries)
            doctors = sorted({e.doctor for e in entries})
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

    # cc.exam_type ja carrega a lateralidade no proprio valor
    # ('RM_JOELHO_D' / 'RM_JOELHO_E' — unicos exam_type deste vertical),
    # entao nao precisa de outro JOIN so para saber o lado do exame de
    # origem da frase.
    rows = conn.execute(
        """
        SELECT cc.sentence_id, cc.structure, cc.finding, cc.status, cc.severity,
               cc.location, cc.section_type, cc.doctor, cc.exam_type, s.text_raw
        FROM clinical_concepts cc
        JOIN sentences s ON cc.sentence_id = s.id
        """
    ).fetchall()
    for (sentence_id, structure, finding, status, severity, location,
         section_type, doctor, exam_type, text) in rows:
        key = (structure, finding, status, severity, location, section_type)
        is_clean = concept_count_by_sentence.get(sentence_id, 1) == 1
        laterality = exam_type.rsplit("_", 1)[-1] if exam_type and "_" in exam_type else None
        if laterality not in ("D", "E"):
            laterality = None
        bank.add(key, doctor, text, clean=is_clean, laterality=laterality)
    return bank
