#!/usr/bin/env python3
"""Fase 1 GLOBAL (Data Engine) — ingestao do corpus radiologico inteiro.

Substitui scripts/ingest_vertical.py, que processava apenas
RM_JOELHO_D/RM_JOELHO_E (911 de 8.402 laudos). Aqui todos os laudos,
modalidades, dominios, tipos de exame e medicos sao ingeridos — ver
PROMPT MESTRE V2, secao 4 (cobertura global obrigatoria) e ADR 0011.

Pipeline (comando unico, idempotente):
  RAW jsonl -> selecao/validacao de snapshot -> normalizacao
  (raw/clean/normalized) -> hashes -> section parser global
  -> sentence parser -> SQLite -> QA_REPORT_FASE1.json

Selecao de snapshot: NAO usa apenas o maior manifest.records. Valida
que o candidato e' superconjunto real dos demais E que os registros
comuns tem texto identico; um conflito falha fechado (levantado pela
auditoria externa como risco; ver validate_snapshots()).

Uso:
    python3 scripts/ingest_corpus.py
    python3 scripts/ingest_corpus.py --exam-type RM_JOELHO_D RM_JOELHO_E
"""

from __future__ import annotations

import argparse
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
SOURCE_LABEL = "CMS_RADIOLOGY_CORPUS_PRODUCTION_V2_1_1_3MONTHS_FAST_AUDITED"


def _load_snapshot(snapshot_dir: Path) -> dict[int, dict]:
    records: dict[int, dict] = {}
    for fpath in sorted(snapshot_dir.glob("reports_*.jsonl")):
        with fpath.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                records[rec["record_id"]] = rec
    return records


def validate_snapshots(raw_root: Path) -> tuple[Path, dict]:
    """Escolhe o snapshot e VALIDA a escolha, em vez de confiar no
    manifest. Falha fechada se o candidato nao for superconjunto dos
    demais ou se um registro comum tiver texto divergente — nesse caso
    nao existe 'o mais recente', existe um conflito que precisa de
    decisao humana."""
    snapshots = sorted(p for p in raw_root.iterdir() if p.is_dir() and (p / "manifest.json").exists())
    if not snapshots:
        raise SystemExit(f"Nenhum snapshot com manifest.json em {raw_root}")

    loaded = {snap: _load_snapshot(snap) for snap in snapshots}
    candidate = max(loaded, key=lambda s: len(loaded[s]))

    report = {"candidate": candidate.name, "candidate_records": len(loaded[candidate]),
               "compared_with": []}
    for snap, recs in loaded.items():
        if snap is candidate:
            continue
        missing = sorted(set(recs) - set(loaded[candidate]))
        divergent = [
            rid for rid in (set(recs) & set(loaded[candidate]))
            if exact_hash(recs[rid].get("report_text", ""))
            != exact_hash(loaded[candidate][rid].get("report_text", ""))
        ]
        report["compared_with"].append({
            "snapshot": snap.name, "records": len(recs),
            "records_missing_from_candidate": len(missing),
            "records_with_divergent_text": len(divergent),
        })
        if missing or divergent:
            raise SystemExit(
                f"CONFLITO DE SNAPSHOT: {snap.name} tem {len(missing)} registros ausentes "
                f"e {len(divergent)} com texto divergente em relacao a {candidate.name}. "
                "Nao existe superconjunto seguro — decisao humana necessaria."
            )

    manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
    report["manifest_declared_records"] = manifest.get("records")
    report["manifest_matches_actual"] = manifest.get("records") == len(loaded[candidate])
    return candidate, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-type", nargs="*", default=None,
                         help="Restringe a tipos de exame (padrao: TODOS — nao use sem motivo).")
    args = parser.parse_args()

    snapshot_dir, snapshot_report = validate_snapshots(RAW_ROOT)
    import_batch = snapshot_dir.name
    records = list(_load_snapshot(snapshot_dir).values())
    if args.exam_type:
        wanted = set(args.exam_type)
        records = [r for r in records if r.get("exam_type") in wanted]
    records.sort(key=lambda r: r["record_id"])

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    rebuild_schema(conn)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    section_type_coverage: dict[str, Counter] = defaultdict(Counter)
    doctor_totals: Counter = Counter()
    modality_totals: Counter = Counter()
    exam_type_totals: Counter = Counter()
    domain_totals: Counter = Counter()
    unmatched_headers: Counter = Counter()
    unmatched_by_modality: Counter = Counter()
    reports_without_findings: Counter = Counter()
    implicit_findings: Counter = Counter()
    report_exact_hashes: Counter = Counter()
    sentence_exact_hashes: Counter = Counter()
    total_sentences = 0
    sentences_by_modality: Counter = Counter()
    patients: set = set()

    for rec in records:
        raw_text = rec["report_text"]
        clean_text = clean(raw_text)
        norm_text = normalized(clean_text)
        r_exact = exact_hash(clean_text)
        r_norm = normalized_hash(norm_text)
        modality = rec["modality"]

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
                rec["exam_datetime"], modality, rec["domain"], rec["anatomy"],
                rec["laterality"], rec["exam_type"], rec["study_description_raw"],
                rec["doctor"], raw_text, clean_text, norm_text, r_exact, r_norm,
                SOURCE_LABEL, import_batch, now,
            ),
        )
        report_id = cur.lastrowid

        report_exact_hashes[r_exact] += 1
        doctor_totals[rec["doctor"]] += 1
        modality_totals[modality] += 1
        exam_type_totals[rec["exam_type"]] += 1
        domain_totals[rec["domain"]] += 1
        patients.add(rec["patient_id"])

        parse_result = parse_sections(clean_text)
        types_found = set()

        for section in parse_result.sections:
            section_clean = clean(section.text_raw)
            cur.execute(
                """INSERT INTO report_sections (
                    report_id, section_type, section_order, text_raw,
                    text_clean, header_line, unmatched_header, section_subtype
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    report_id, section.section_type, section.section_order,
                    section.text_raw, section_clean, section.header_line,
                    int(section.unmatched_header), section.section_subtype,
                ),
            )
            section_id = cur.lastrowid
            types_found.add(section.section_type)
            if (section.section_subtype or "").startswith("implicit"):
                implicit_findings[section.section_subtype] += 1

            for order, sent in enumerate(split_sentences(section_clean)):
                sent_norm = normalized(sent)
                cur.execute(
                    """INSERT INTO sentences (
                        report_id, section_id, sentence_order, text_raw,
                        text_normalized, doctor, exam_type, exact_hash, normalized_hash
                    ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        report_id, section_id, order, sent, sent_norm,
                        rec["doctor"], rec["exam_type"], exact_hash(sent),
                        normalized_hash(sent_norm),
                    ),
                )
                sentence_exact_hashes[exact_hash(sent)] += 1
                total_sentences += 1
                sentences_by_modality[modality] += 1

        for st in types_found:
            section_type_coverage[rec["doctor"]][st] += 1
        if "findings" not in types_found:
            reports_without_findings[modality] += 1
        if parse_result.unmatched_header_candidates:
            unmatched_by_modality[modality] += 1
        for h in parse_result.unmatched_header_candidates:
            unmatched_headers[h] += 1

    conn.commit()

    coverage_by_doctor = {}
    for doctor, total in doctor_totals.items():
        found = section_type_coverage[doctor]
        coverage_by_doctor[doctor] = {
            "total_reports": total,
            **{f"pct_with_{t}": round(100 * found.get(t, 0) / total, 1)
               for t in ("indication", "technique", "findings", "impression", "comparison")},
        }

    dupe_groups = {h: n for h, n in report_exact_hashes.items() if n > 1}
    qa = {
        "generated_at": now,
        "phase": "1_global",
        "scope": "corpus completo" if not args.exam_type else f"filtrado: {sorted(args.exam_type)}",
        "snapshot_validation": snapshot_report,
        "totals": {
            "reports": len(records),
            "patients_distinct": len(patients),
            "sentences": total_sentences,
            "modalities": dict(modality_totals.most_common()),
            "domains": dict(domain_totals.most_common()),
            "exam_types_distinct": len(exam_type_totals),
            "doctors_distinct": len(doctor_totals),
            "sentences_by_modality": dict(sentences_by_modality.most_common()),
        },
        "parser_quality": {
            "reports_with_unmatched_header_by_modality": {
                m: {"n": unmatched_by_modality.get(m, 0),
                    "pct": round(100 * unmatched_by_modality.get(m, 0) / n, 1)}
                for m, n in modality_totals.items()
            },
            "reports_without_findings_section_by_modality": {
                m: {"n": reports_without_findings.get(m, 0),
                    "pct": round(100 * reports_without_findings.get(m, 0) / n, 1)}
                for m, n in modality_totals.items()
            },
            "implicit_findings_sections": dict(implicit_findings.most_common()),
            "unmatched_header_labels_distinct": len(unmatched_headers),
            "unmatched_header_top": unmatched_headers.most_common(40),
        },
        "duplication": {
            "report_text_duplicate_groups": len(dupe_groups),
            "reports_in_duplicate_groups": sum(dupe_groups.values()),
            "note": ("Texto de laudo exatamente repetido entre exames distintos. "
                      "Precisa ser controlado em qualquer estatistica de associacao "
                      "(inflaria coocorrencia); ver Fase 4D."),
        },
        "coverage_by_doctor": coverage_by_doctor,
        "exam_type_totals": exam_type_totals.most_common(),
    }

    QA_DIR.mkdir(parents=True, exist_ok=True)
    (QA_DIR / "QA_REPORT_FASE1.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Snapshot validado: {snapshot_dir.name}")
    print(f"Laudos ingeridos: {len(records)} | pacientes: {len(patients)} | sentencas: {total_sentences}")
    print(f"Modalidades: {dict(modality_totals.most_common())}")
    print(f"Tipos de exame: {len(exam_type_totals)} | medicos: {len(doctor_totals)}")
    for m, n in modality_totals.most_common():
        u = unmatched_by_modality.get(m, 0)
        nf = reports_without_findings.get(m, 0)
        print(f"  {m}: cabecalho nao reconhecido {u} ({100*u/n:.1f}%) | "
               f"sem secao findings {nf} ({100*nf/n:.1f}%)")
    print(f"Grupos de texto duplicado: {len(dupe_groups)} ({sum(dupe_groups.values())} laudos)")
    print(f"Banco: {DB_PATH}")
    print(f"QA: {QA_DIR / 'QA_REPORT_FASE1.json'}")


if __name__ == "__main__":
    main()
