"""Deteccao de ambiguidade clinica genuina — Fase 4/6.

Regra do usuario: quando ha ambiguidade clinica real, o sistema NAO
deve forcar uma classificacao artificial. O texto original e sempre
preservado (ja e o comportamento de knee_concepts.py: nunca reescreve,
so extrai). Este modulo identifica os casos que devem ir para revisao
humana em vez de serem tratados como extracao normal — cada caso e
sinalizado, nunca escondido nem decidido por adivinhacao.

Criterios usados (todos com evidencia real no corpus, nao especulados):

1. linguagem de hedge/incerteza no texto original (ex.: 'sugestivo de',
   'não se pode excluir') — a INCERTEZA e do proprio radiologista que
   redigiu o laudo, o sistema so a torna visivel.
2. contexto pos-cirurgico/reconstrucao — um achado descrito apos
   'reconstrução', 'enxerto', 'meniscectomia' pode se referir a
   estrutura nativa OU ao material cirurgico; decidir qual, sem contexto
   adicional, seria adivinhacao.
3. multiplas medidas na mesma sentenca — nao e seguro assumir qual
   medida corresponde ao achado extraido quando ha mais de uma.
4. faixa de grau com mais de 2 valores (ex.: hipotetico 'grau I/II/III')
   — o parser so captura os dois primeiros; qualquer valor alem disso
   ficaria silenciosamente descartado se nao fosse sinalizado.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from dataclasses import dataclass

from backend.clinical.knee_concepts import ClinicalConcept, _MEASUREMENT_RE, _HEDGE_CUES

_POST_SURGICAL_CUES = [
    "reconstrução", "reconstrucao", "reconstruído", "reconstruido",
    "pós-operatório", "pos-operatorio", "pós operatório",
    "manipulação cirúrgica", "manipulacao cirurgica",
    "meniscectomia", "enxerto", "neoligamento",
]

_GRADE_OVERFLOW_RE = re.compile(
    r"grau\s*(?:i{1,3}v?|iv|[1-4])\s*[/\-]\s*(?:i{1,3}v?|iv|[1-4])\s*[/\-]\s*(?:i{1,3}v?|iv|[1-4])"
)


@dataclass
class ReviewQueueItem:
    reason: str
    risk_level: str  # low | medium | high
    rule_id: str | None
    detail: str


def detect_ambiguities(
    text_normalized: str, concepts: list[ClinicalConcept],
) -> list[ReviewQueueItem]:
    items: list[ReviewQueueItem] = []

    equivocal = [c for c in concepts if c.certainty == "equivocal"]
    if equivocal:
        has_present_pathology = any(c.status == "present" for c in equivocal)
        items.append(ReviewQueueItem(
            reason="hedge_language",
            risk_level="medium" if has_present_pathology else "low",
            rule_id=equivocal[0].rule_id,
            detail=(
                "Texto contém linguagem de incerteza diagnóstica "
                f"({', '.join(c for c in _HEDGE_CUES if c in text_normalized)}); "
                "conceito extraído mantém certainty='equivocal', mas o grau real "
                "de confiança do achado deve ser confirmado pelo médico."
            ),
        ))

    if concepts and any(cue in text_normalized for cue in _POST_SURGICAL_CUES):
        items.append(ReviewQueueItem(
            reason="post_surgical_context",
            risk_level="high",
            rule_id=None,
            detail=(
                "Sentença contém termo de contexto pós-cirúrgico/reconstrução. "
                "O(s) achado(s) extraído(s) pode(m) se referir à estrutura nativa "
                "ou ao material de reconstrução/enxerto — o extrator não distingue "
                "os dois casos; não forçar essa distinção automaticamente."
            ),
        ))

    if len(_MEASUREMENT_RE.findall(text_normalized)) >= 2:
        items.append(ReviewQueueItem(
            reason="multiple_measurements",
            risk_level="low",
            rule_id=None,
            detail=(
                "Mais de uma medida (em cm) na mesma sentença — não é seguro "
                "assumir automaticamente qual medida corresponde ao achado extraído."
            ),
        ))

    if _GRADE_OVERFLOW_RE.search(text_normalized):
        items.append(ReviewQueueItem(
            reason="grade_range_overflow",
            risk_level="low",
            rule_id=None,
            detail=(
                "Faixa de grau com 3 ou mais valores (ex.: 'grau I/II/III') — "
                "o extrator captura apenas os dois primeiros valores da faixa."
            ),
        ))

    return items


# ---- persistencia (upsert que preserva julgamento humano) --------------
#
# Chave natural: (sentence_id, reason). Reexecutar a extracao NUNCA
# apaga uma revisao ja feita (status/reviewer_note de um item existente
# sao preservados pelo ON CONFLICT abaixo). Itens que deixam de ser
# ambiguos (ex.: um bug de extracao foi corrigido) sao removidos.

QueueRowKey = tuple[int, str]  # (sentence_id, reason)
QueueRowValues = tuple  # (report_id, sentence_id, section_type, doctor, exam_type,
#                          original_text, system_output_json, rule_id, reason, risk_level)


def sync_review_queue(
    cur: sqlite3.Cursor, current_rows: list[tuple[QueueRowKey, QueueRowValues]],
) -> tuple[int, int]:
    """Aplica o conjunto atual de itens ambiguos: insere novos, atualiza
    o conteudo de existentes (preservando status/reviewer_note/resolved_at),
    remove os que nao aparecem mais. Retorna (sincronizados, removidos)."""
    now = datetime.now(timezone.utc).isoformat()
    for (sentence_id, reason), row in current_rows:
        cur.execute(
            """INSERT INTO clinical_review_queue (
                report_id, sentence_id, section_type, doctor, exam_type,
                original_text, system_output_json, rule_id, reason, risk_level,
                status, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,'pending',?)
            ON CONFLICT(sentence_id, reason) DO UPDATE SET
                report_id=excluded.report_id,
                section_type=excluded.section_type,
                doctor=excluded.doctor,
                exam_type=excluded.exam_type,
                original_text=excluded.original_text,
                system_output_json=excluded.system_output_json,
                rule_id=excluded.rule_id,
                risk_level=excluded.risk_level
            """,
            (*row, now),
        )

    current_key_set = {k for k, _ in current_rows}
    existing = cur.execute("SELECT id, sentence_id, reason FROM clinical_review_queue").fetchall()
    stale_ids = [rid for rid, sid, reason in existing if (sid, reason) not in current_key_set]
    if stale_ids:
        cur.executemany("DELETE FROM clinical_review_queue WHERE id = ?", [(i,) for i in stale_ids])
    return len(current_rows), len(stale_ids)


def resolve_review_item(cur: sqlite3.Cursor, item_id: int, reviewer_note: str | None) -> bool:
    """Marca um item da fila como resolvido, com nota opcional do
    revisor. Retorna False se o item nao existir."""
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        "UPDATE clinical_review_queue SET status='resolved', reviewer_note=?, resolved_at=? WHERE id=?",
        (reviewer_note, now, item_id),
    )
    return cur.rowcount > 0


def reopen_review_item(cur: sqlite3.Cursor, item_id: int) -> bool:
    cur.execute(
        "UPDATE clinical_review_queue SET status='pending', resolved_at=NULL WHERE id=?",
        (item_id,),
    )
    return cur.rowcount > 0
