#!/usr/bin/env python3
"""Fase 1 (Data Engine) — ingestao de um vertical unico.

Vertical piloto: RM_JOELHO_D + RM_JOELHO_E (911 exames, MSK), escolhido
por ser o de maior volume dentro da subespecialidade do usuario — ver
docs/architecture.md para a justificativa de restringir a um vertical
antes de generalizar.

Pipeline (por comando unico, idempotente):
  RAW jsonl -> normalizacao (raw/clean/normalized) -> A/B hashes
  -> section parser -> sentence parser -> persistencia (SQLite)
  -> QA_REPORT_FASE1.json

Uso:
    python3 scripts/ingest_vertical.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.normalization.text_normalization import (  # noqa: E402
    clean, normalized, exact_hash, normalized_hash,
)
from backend.parsers.section_parser import parse_sections  # noqa: E402
from backend.parsers.sentence_parser import split_sentences  # noqa: E402
from backend.db.schema import rebuild_schema  # noqa: E402

RAW_ROOT = ROOT / "data" / "raw" / "CMS_CORPUS_2026-06-06_A_2026-09-06"
DB_PATH = ROOT / "data" / "processed" / "laudocore.db"
QA_DIR = ROOT / "data" / "derived" / "qa"

VERTICAL_EXAM_TYPES = {"RM_JOELHO_D", "RM_JOELHO_E"}
SOURCE_LABEL = "CMS_RADIOLOGY_CORPUS_PRODUCTION_V2_1_1_3MONTHS_FAST_AUDITED"


def pick_latest_snapshot(raw_root: Path) -> Path:
    candidates = [p for p in raw_root.iterdir() if p.is_dir()]
    best, best_count = None, -1
    for snap in candidates:
        manifest_path = snap / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        declared = manifest.get("records", -1)
        if declared > best_count:
            best_count, best = declared, snap
    if best is None:
        raise SystemExit(f"Nenhum manifest.json valido em {raw_root}")
    return best


def load_vertical_records(snapshot_dir: Path) -> list[dict]:
    records = []
    for fpath in sorted(snapshot_dir.glob("reports_*.jsonl")):
        with fpath.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("exam_type") in VERTICAL_EXAM_TYPES:
                    records.append(rec)
    return records


def main() -> None:
    snapshot_dir = pick_latest_snapshot(RAW_ROOT)
    import_batch = snapshot_dir.name
    records = load_vertical_records(snapshot_dir)
    records.sort(key=lambda r: r["record_id"])  # ordem deterministica

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    rebuild_schema(conn)  # rebuild completo a cada execucao: idempotente
                            # neste volume (~900 registros); ver ADR 0004.
    cur = conn.cursor()

    now = datetime.now(timezone.utc).isoformat()

    section_type_coverage: dict[str, Counter] = defaultdict(Counter)  # doctor -> Counter(section_type)
    doctor_totals: Counter = Counter()
    unmatched_headers: Counter = Counter()
    report_exact_hashes: Counter = Counter()
    report_normalized_hashes: Counter = Counter()
    sentence_exact_hashes: Counter = Counter()
    total_sentences = 0
    sentences_per_report = []

    for rec in records:
        raw_text = rec["report_text"]
        clean_text = clean(raw_text)
        norm_text = normalized(clean_text)
        r_exact = exact_hash(clean_text)
        r_norm = normalized_hash(norm_text)

        cur.execute(
            """INSERT INTO reports (
                record_id, patient_id, age_at_exam, sex, exam_datetime,
                modality, domain, anatomy, laterality, exam_type,
                study_description_raw, doctor, report_text_raw,
                report_text_clean, report_text_normalized,
                exact_hash, normalized_hash, source, import_batch, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rec["record_id"], rec["patient_id"], rec["age_at_exam"], rec["sex"],
                rec["exam_datetime"], rec["modality"], rec["domain"], rec["anatomy"],
                rec["laterality"], rec["exam_type"], rec["study_description_raw"],
                rec["doctor"], raw_text, clean_text, norm_text, r_exact, r_norm,
                SOURCE_LABEL, import_batch, now,
            ),
        )
        report_id = cur.lastrowid

        report_exact_hashes[r_exact] += 1
        report_normalized_hashes[r_norm] += 1
        doctor_totals[rec["doctor"]] += 1

        parse_result = parse_sections(clean_text)
        types_found_this_report = set()
        report_sentence_count = 0

        for section in parse_result.sections:
            section_clean = clean(section.text_raw)
            cur.execute(
                """INSERT INTO report_sections (
                    report_id, section_type, section_order, text_raw,
                    text_clean, header_line, unmatched_header
                ) VALUES (?,?,?,?,?,?,?)""",
                (
                    report_id, section.section_type, section.section_order,
                    section.text_raw, section_clean, section.header_line,
                    int(section.unmatched_header),
                ),
            )
            section_id = cur.lastrowid
            types_found_this_report.add(section.section_type)

            for order, sent in enumerate(split_sentences(section_clean)):
                sent_norm = normalized(sent)
                s_exact = exact_hash(sent)
                s_norm = normalized_hash(sent_norm)
                cur.execute(
                    """INSERT INTO sentences (
                        report_id, section_id, sentence_order, text_raw,
                        text_normalized, doctor, exam_type, exact_hash, normalized_hash
                    ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        report_id, section_id, order, sent, sent_norm,
                        rec["doctor"], rec["exam_type"], s_exact, s_norm,
                    ),
                )
                sentence_exact_hashes[s_exact] += 1
                total_sentences += 1
                report_sentence_count += 1

        sentences_per_report.append(report_sentence_count)
        for st in types_found_this_report:
            section_type_coverage[rec["doctor"]][st] += 1
        for h in parse_result.unmatched_header_candidates:
            unmatched_headers[h] += 1

    conn.commit()

    # ---- QA da Fase 1 ----
    coverage_report = {}
    for doctor, total in doctor_totals.items():
        found = section_type_coverage[doctor]
        coverage_report[doctor] = {
            "total_reports": total,
            "pct_with_indication": round(100 * found.get("indication", 0) / total, 1),
            "pct_with_technique": round(100 * found.get("technique", 0) / total, 1),
            "pct_with_findings": round(100 * found.get("findings", 0) / total, 1),
            "pct_with_impression": round(100 * found.get("impression", 0) / total, 1),
            "pct_with_comparison": round(100 * found.get("comparison", 0) / total, 1),
        }

    report_exact_dupe_groups = sum(1 for c in report_exact_hashes.values() if c > 1)
    report_exact_dupe_records = sum(c for c in report_exact_hashes.values() if c > 1)
    sentence_dupe_groups = sum(1 for c in sentence_exact_hashes.values() if c > 1)
    sentence_dupe_records = sum(c for c in sentence_exact_hashes.values() if c > 1)

    qa = {
        "generated_at": now,
        "vertical": sorted(VERTICAL_EXAM_TYPES),
        "snapshot_used": import_batch,
        "totals": {
            "reports_ingested": len(records),
            "sentences_extracted": total_sentences,
            "sentences_per_report": {
                "min": min(sentences_per_report) if sentences_per_report else None,
                "max": max(sentences_per_report) if sentences_per_report else None,
                "mean": round(sum(sentences_per_report) / len(sentences_per_report), 1)
                if sentences_per_report else None,
            },
        },
        "section_coverage_by_doctor": coverage_report,
        "unmatched_header_candidates": dict(unmatched_headers.most_common()),
        "unmatched_header_total_occurrences": sum(unmatched_headers.values()),
        "report_level_duplicates": {
            "note": "Informativo — NAO removido. Mesmo texto pode corresponder a "
                    "exames reais distintos (ex.: laudo padrao de normalidade).",
            "exact_groups": report_exact_dupe_groups,
            "exact_records": report_exact_dupe_records,
        },
        "sentence_level_duplicates": {
            "note": "Informativo — frases identicas entre laudos sao esperadas "
                    "(vocabulario padronizado) e serao a base da biblioteca de "
                    "frases na Fase 3, nao um defeito de qualidade.",
            "exact_groups": sentence_dupe_groups,
            "exact_records": sentence_dupe_records,
        },
    }

    QA_DIR.mkdir(parents=True, exist_ok=True)
    (QA_DIR / "QA_REPORT_FASE1.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    conn.close()

    print(f"Snapshot: {import_batch}")
    print(f"Laudos ingeridos: {len(records)} | sentencas extraidas: {total_sentences}")
    print(f"Cabecalhos nao reconhecidos (ocorrencias): {sum(unmatched_headers.values())}")
    print(f"Duplicatas exatas de laudo: {report_exact_dupe_groups} grupos / {report_exact_dupe_records} registros")
    print(f"Banco: {DB_PATH}")
    print(f"QA: {QA_DIR / 'QA_REPORT_FASE1.json'}")


if __name__ == "__main__":
    main()
