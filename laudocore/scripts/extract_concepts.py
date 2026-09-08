#!/usr/bin/env python3
"""Fase 4 (Clinical Concept Layer) — vertical piloto RM de joelho.

Le as sentencas de achados/impressao ja persistidas pela Fase 1
(scripts/ingest_vertical.py) e aplica extracao por regras (sem LLM,
ver backend/clinical/knee_concepts.py), persistindo em
clinical_concepts e populando a fila de revisao clinica
(clinical_review_queue) para casos de ambiguidade genuina (ver
backend/clinical/review_queue.py) — nunca forcando uma classificacao
quando ha duvida real. Gera:

  data/derived/qa/QA_REPORT_FASE4.json          (commitado — agregados)
  data/derived/qa/FASE4_manual_review_sample.json (NAO commitado — contem
                                                     texto real de sentenca,
                                                     ver docs/decisions/0002)

A fila de revisao (clinical_review_queue) usa UPSERT por chave natural
(sentence_id, reason): reexecutar este script NUNCA apaga uma revisao
humana ja feita (status/reviewer_note sao preservados). Itens que nao
sao mais ambiguos (ex.: um bug corrigido) sao removidos automaticamente.

Uso:
    python3 scripts/extract_concepts.py

Pre-requisito: rodar scripts/ingest_vertical.py antes (schema de
sentences precisa existir e estar populado).
"""

from __future__ import annotations

import json
import random
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.clinical.knee_concepts import extract_concepts  # noqa: E402
from backend.clinical.review_queue import detect_ambiguities, sync_review_queue  # noqa: E402
from backend.db.schema import rebuild_concepts_schema, ensure_review_queue_schema  # noqa: E402

DB_PATH = ROOT / "data" / "processed" / "laudocore.db"
QA_DIR = ROOT / "data" / "derived" / "qa"

RELEVANT_SECTION_TYPES = ("findings", "impression")


def _concepts_summary(concepts) -> str:
    return json.dumps([
        {
            "structure": c.structure, "finding": c.finding, "status": c.status,
            "severity": c.severity, "location": c.location,
            "measurement_cm": c.measurement_cm, "certainty": c.certainty,
            "rule_id": c.rule_id,
        }
        for c in concepts
    ], ensure_ascii=False)


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(
            f"{DB_PATH} nao existe. Rode scripts/ingest_vertical.py primeiro."
        )

    conn = sqlite3.connect(DB_PATH)
    rebuild_concepts_schema(conn)
    ensure_review_queue_schema(conn)
    cur = conn.cursor()

    sentences = cur.execute(
        f"""
        SELECT s.id, s.report_id, s.text_raw, s.text_normalized, s.doctor, s.exam_type, rs.section_type
        FROM sentences s
        JOIN report_sections rs ON s.section_id = rs.id
        WHERE rs.section_type IN ({",".join("?" for _ in RELEVANT_SECTION_TYPES)})
        ORDER BY s.id
        """,
        RELEVANT_SECTION_TYPES,
    ).fetchall()

    total_sentences = len(sentences)
    sentences_with_concept = 0
    concept_rows_to_insert = []
    finding_counter: Counter = Counter()
    structure_counter: Counter = Counter()
    rule_counter: Counter = Counter()
    zero_concept_sentence_ids = []
    review_queue_rows: list[tuple] = []
    review_reason_counter: Counter = Counter()
    review_risk_counter: Counter = Counter()

    for sent_id, report_id, text_raw, text_norm, doctor, exam_type, section_type in sentences:
        result = extract_concepts(text_norm)
        if result.concepts:
            sentences_with_concept += 1
        else:
            zero_concept_sentence_ids.append(sent_id)

        for c in result.concepts:
            finding_counter[c.finding] += 1
            structure_counter[c.structure] += 1
            rule_counter[c.rule_id] += 1
            concept_rows_to_insert.append((
                report_id, sent_id, section_type, c.organ, c.structure, c.finding,
                c.status, c.severity, c.location, c.measurement_cm, c.certainty,
                c.rule_id, doctor, exam_type,
            ))

        for item in detect_ambiguities(text_norm, result.concepts):
            review_reason_counter[item.reason] += 1
            review_risk_counter[item.risk_level] += 1
            review_queue_rows.append((
                (sent_id, item.reason),
                (report_id, sent_id, section_type, doctor, exam_type,
                 text_raw, _concepts_summary(result.concepts), item.rule_id,
                 item.reason, item.risk_level),
            ))

    # Cabecalhos de secao nao reconhecidos (Fase 1) tambem sao ambiguidade
    # genuina: o sistema explicitamente nao sabe classificar aquele
    # trecho. Ancora no primeiro sentence_id da propria secao 'other'.
    unmatched_sections = cur.execute(
        """
        SELECT rs.id, rs.report_id, rs.header_line, rs.text_raw, r.doctor, r.exam_type
        FROM report_sections rs JOIN reports r ON rs.report_id = r.id
        WHERE rs.unmatched_header = 1
        """
    ).fetchall()
    for section_id, report_id, header_line, section_text_raw, doctor, exam_type in unmatched_sections:
        anchor = cur.execute(
            "SELECT id FROM sentences WHERE section_id = ? ORDER BY sentence_order LIMIT 1",
            (section_id,),
        ).fetchone()
        if anchor is None:
            continue
        sent_id = anchor[0]
        review_reason_counter["unmatched_header"] += 1
        review_risk_counter["medium"] += 1
        review_queue_rows.append((
            (sent_id, "unmatched_header"),
            (report_id, sent_id, "other", doctor, exam_type,
             section_text_raw, "[]", None, "unmatched_header", "medium"),
        ))

    cur.executemany(
        """INSERT INTO clinical_concepts (
            report_id, sentence_id, section_type, organ, structure, finding,
            status, severity, location, measurement_cm, certainty, rule_id,
            doctor, exam_type
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        concept_rows_to_insert,
    )

    synced_count, removed_stale_count = sync_review_queue(cur, review_queue_rows)
    conn.commit()

    coverage_pct = round(100 * sentences_with_concept / total_sentences, 1) if total_sentences else 0.0

    pending_count = cur.execute(
        "SELECT COUNT(*) FROM clinical_review_queue WHERE status = 'pending'"
    ).fetchone()[0]

    qa = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vertical": ["RM_JOELHO_D", "RM_JOELHO_E"],
        "method": "regras/regex, sem LLM (ver backend/clinical/knee_concepts.py)",
        "totals": {
            "sentences_considered": total_sentences,
            "sentences_with_at_least_one_concept": sentences_with_concept,
            "coverage_pct_approx_recall": coverage_pct,
            "concepts_extracted": len(concept_rows_to_insert),
        },
        "caveat": (
            "coverage_pct_approx_recall mede apenas se pelo menos um conceito foi "
            "extraido por sentenca — NAO mede precisao (se o conceito extraido "
            "esta correto). Ver docs/decisions/0007 para a metodologia de "
            "verificacao de fidelidade textual ja aplicada e suas limitacoes."
        ),
        "concepts_by_finding": dict(finding_counter.most_common()),
        "concepts_by_structure": dict(structure_counter.most_common()),
        "concepts_by_rule": dict(rule_counter.most_common()),
        "sentences_without_concept_count": len(zero_concept_sentence_ids),
        "clinical_review_queue": {
            "note": "Casos de ambiguidade clinica genuina — nao classificados "
                    "automaticamente por design. Ver fila completa na aplicacao "
                    "(nao commitada — contem texto real, ver ADR 0002).",
            "current_items_synced": synced_count,
            "pending_total": pending_count,
            "stale_items_auto_removed_this_run": removed_stale_count,
            "by_reason": dict(review_reason_counter.most_common()),
            "by_risk_level": dict(review_risk_counter.most_common()),
        },
    }

    QA_DIR.mkdir(parents=True, exist_ok=True)
    (QA_DIR / "QA_REPORT_FASE4.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---- amostra para revisao humana (NAO commitada — contem texto real) ----
    rng = random.Random(42)  # seed fixa: reprodutibilidade da amostra
    sentences_by_id = {row[0]: row for row in sentences}

    matched_ids = [sid for sid, *_ in sentences if sid not in zero_concept_sentence_ids]
    sample_matched = rng.sample(matched_ids, min(30, len(matched_ids)))
    sample_zero = rng.sample(zero_concept_sentence_ids, min(30, len(zero_concept_sentence_ids)))

    def render_sample(sent_id: int) -> dict:
        _, report_id, _text_raw, text_norm, doctor, exam_type, section_type = sentences_by_id[sent_id]
        result = extract_concepts(text_norm)
        return {
            "sentence_id": sent_id,
            "report_id": report_id,
            "doctor": doctor,
            "text_normalized": text_norm,
            "extracted_concepts": [
                {
                    "structure": c.structure, "finding": c.finding, "status": c.status,
                    "severity": c.severity, "location": c.location,
                    "measurement_cm": c.measurement_cm, "certainty": c.certainty,
                    "rule_id": c.rule_id,
                }
                for c in result.concepts
            ],
        }

    review_sample = {
        "generated_at": qa["generated_at"],
        "note": "Amostra para revisao humana manual (precisao). NAO commitar — "
                "contem texto real de sentenca. Ver docs/decisions/0002.",
        "sample_with_concepts": [render_sample(i) for i in sample_matched],
        "sample_without_concepts": [render_sample(i) for i in sample_zero],
    }
    (QA_DIR / "FASE4_manual_review_sample.json").write_text(
        json.dumps(review_sample, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    conn.close()

    print(f"Sentencas consideradas (findings/impression): {total_sentences}")
    print(f"Com >=1 conceito extraido: {sentences_with_concept} ({coverage_pct}%)")
    print(f"Total de conceitos extraidos: {len(concept_rows_to_insert)}")
    print(f"Fila de revisao clinica: {pending_count} pendentes ({synced_count} sincronizados, "
          f"{removed_stale_count} removidos por nao serem mais ambiguos)")
    print(f"QA: {QA_DIR / 'QA_REPORT_FASE4.json'}")
    print(f"Amostra p/ revisao manual (NAO commitar): {QA_DIR / 'FASE4_manual_review_sample.json'}")


if __name__ == "__main__":
    main()
