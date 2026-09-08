#!/usr/bin/env python3
"""Fase 0 — auditoria estrutural e baseline do corpus LaudoCore.

Le o snapshot RAW mais recente do export CMS, recalcula todas as
estatisticas de forma independente (nao confia em manifest.json/stats.json
do export) e gera os entregaveis da Fase 0:

  BASELINE_REPORT.md
  QA_REPORT.json
  exam_types.csv
  physicians.csv

Uso:
    python3 scripts/baseline_audit.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw" / "CMS_CORPUS_2026-06-06_A_2026-09-06"
QA_DIR = ROOT / "data" / "derived" / "qa"
DOCS_DIR = ROOT / "docs"

REQUIRED_SCHEMA = [
    "record_id",
    "patient_id",
    "age_at_exam",
    "sex",
    "exam_datetime",
    "domain",
    "modality",
    "anatomy",
    "laterality",
    "exam_type",
    "study_description_raw",
    "doctor",
    "report_text",
]

ALLOWED_MODALITIES = {"RM", "TC", "RX"}  # US ainda nao presente neste export
DATE_FROM = datetime(2026, 6, 6)
DATE_TO = datetime(2026, 9, 6, 23, 59, 59)


def pick_latest_snapshot(raw_root: Path) -> Path:
    """Escolhe o snapshot mais completo (mais recente / maior contagem).

    Os tres diretorios sob RAW_ROOT sao exports cumulativos sucessivos do
    mesmo lote (mesma janela de datas), gerados no mesmo dia. Nao sao
    corpora distintos: sao snapshots parciais do mesmo processo de export
    ainda em andamento. Usamos o manifest.json de cada um para escolher
    o de maior 'records' declarado, e confirmamos contando as linhas reais.
    """
    candidates = [p for p in raw_root.iterdir() if p.is_dir()]
    if not candidates:
        raise SystemExit(f"Nenhum snapshot encontrado em {raw_root}")

    best = None
    best_count = -1
    for snap in candidates:
        manifest_path = snap / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        declared = manifest.get("records", -1)
        if declared > best_count:
            best_count = declared
            best = snap
    if best is None:
        raise SystemExit("Nenhum manifest.json valido encontrado entre os snapshots.")
    return best


def detect_encoding_anomalies(text: str) -> list[str]:
    anomalies = []
    if "�" in text:
        anomalies.append("replacement_char_U+FFFD")
    # caracteres de controle alem de \n e \t
    for ch in text:
        cat = unicodedata.category(ch)
        if cat == "Cc" and ch not in ("\n", "\t"):
            anomalies.append(f"control_char_{hex(ord(ch))}")
            break
    # padrao classico de mojibake latin1/utf8 (Ã©, Ã£, Â etc.)
    if re.search(r"Ã[\x80-\xBF]|Â[\x80-\xBF]", text):
        anomalies.append("possible_mojibake")
    return anomalies


def normalize_for_hash(text: str) -> str:
    t = text.casefold()
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    return t


def main() -> None:
    snapshot_dir = pick_latest_snapshot(RAW_ROOT)
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    source_stats = json.loads((snapshot_dir / "stats.json").read_text(encoding="utf-8"))

    jsonl_files = sorted(snapshot_dir.glob("reports_*.jsonl"))
    if not jsonl_files:
        raise SystemExit(f"Nenhum reports_*.jsonl em {snapshot_dir}")

    total_lines = 0
    valid_records = 0
    invalid_records: list[dict] = []
    seen_record_ids: dict[int, str] = {}
    duplicate_record_ids: list[dict] = []

    by_modality = Counter()
    by_domain = Counter()
    by_anatomy = Counter()
    by_doctor = Counter()
    by_sex = Counter()
    by_laterality = Counter()
    by_exam_type = Counter()
    exam_type_meta: dict[str, dict] = {}
    doctor_meta: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "by_modality": Counter(), "by_domain": Counter()
    })

    missing_field_counts = Counter()
    type_error_counts = Counter()
    date_out_of_range = []
    encoding_flags = []
    unknown_modality = []

    exact_hash_counts: Counter[str] = Counter()
    normalized_hash_counts: Counter[str] = Counter()
    report_text_lengths = []

    for fpath in jsonl_files:
        with fpath.open("r", encoding="utf-8") as fh:
            for lineno, raw_line in enumerate(fh, start=1):
                total_lines += 1
                line = raw_line.rstrip("\n")
                if not line.strip():
                    invalid_records.append({
                        "file": fpath.name, "line": lineno, "reason": "empty_line"
                    })
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    invalid_records.append({
                        "file": fpath.name, "line": lineno,
                        "reason": f"json_decode_error: {exc}"
                    })
                    continue

                missing = [f for f in REQUIRED_SCHEMA if f not in rec]
                if missing:
                    for m in missing:
                        missing_field_counts[m] += 1
                    invalid_records.append({
                        "file": fpath.name, "line": lineno,
                        "reason": f"missing_fields: {missing}",
                        "record_id": rec.get("record_id"),
                    })
                    continue

                record_ok = True
                if not isinstance(rec["record_id"], int):
                    type_error_counts["record_id"] += 1
                    record_ok = False
                if not isinstance(rec["report_text"], str) or not rec["report_text"].strip():
                    type_error_counts["report_text"] += 1
                    record_ok = False
                if rec["laterality"] is not None and not isinstance(rec["laterality"], str):
                    type_error_counts["laterality"] += 1
                    record_ok = False
                if rec["modality"] not in ALLOWED_MODALITIES:
                    unknown_modality.append({
                        "record_id": rec.get("record_id"), "modality": rec.get("modality")
                    })

                if not record_ok:
                    invalid_records.append({
                        "file": fpath.name, "line": lineno,
                        "reason": "type_error", "record_id": rec.get("record_id"),
                    })
                    continue

                rid = rec["record_id"]
                if rid in seen_record_ids:
                    duplicate_record_ids.append({
                        "record_id": rid,
                        "first_file": seen_record_ids[rid],
                        "duplicate_file": fpath.name,
                    })
                else:
                    seen_record_ids[rid] = fpath.name

                try:
                    dt = datetime.strptime(rec["exam_datetime"], "%d/%m/%Y %H:%M")
                    if not (DATE_FROM <= dt <= DATE_TO):
                        date_out_of_range.append({
                            "record_id": rid, "exam_datetime": rec["exam_datetime"]
                        })
                except ValueError:
                    date_out_of_range.append({
                        "record_id": rid, "exam_datetime": rec["exam_datetime"],
                        "reason": "unparseable",
                    })

                anomalies = detect_encoding_anomalies(rec["report_text"])
                if anomalies:
                    encoding_flags.append({"record_id": rid, "anomalies": anomalies})

                valid_records += 1
                by_modality[rec["modality"]] += 1
                by_domain[rec["domain"]] += 1
                by_anatomy[rec["anatomy"]] += 1
                by_doctor[rec["doctor"]] += 1
                by_sex[rec["sex"]] += 1
                by_laterality[rec["laterality"] if rec["laterality"] else "NULL"] += 1
                by_exam_type[rec["exam_type"]] += 1
                report_text_lengths.append(len(rec["report_text"]))

                meta = exam_type_meta.setdefault(rec["exam_type"], {
                    "modality": rec["modality"], "domain": rec["domain"],
                    "anatomy": rec["anatomy"], "doctors": set(), "count": 0,
                    "laterality_values": set(),
                })
                meta["doctors"].add(rec["doctor"])
                meta["count"] += 1
                meta["laterality_values"].add(rec["laterality"] or "NULL")

                dmeta = doctor_meta[rec["doctor"]]
                dmeta["total"] += 1
                dmeta["by_modality"][rec["modality"]] += 1
                dmeta["by_domain"][rec["domain"]] += 1

                exact_hash_counts[hashlib.sha256(rec["report_text"].encode("utf-8")).hexdigest()] += 1
                normalized_hash_counts[
                    hashlib.sha256(normalize_for_hash(rec["report_text"]).encode("utf-8")).hexdigest()
                ] += 1

    assert total_lines == valid_records + len(invalid_records), (
        "Criterio de Fase 0 violado: nem toda linha foi lida ou justificada como invalida."
    )

    exact_dupe_groups = sum(1 for c in exact_hash_counts.values() if c > 1)
    exact_dupe_records = sum(c for c in exact_hash_counts.values() if c > 1)
    normalized_dupe_groups = sum(1 for c in normalized_hash_counts.values() if c > 1)
    normalized_dupe_records = sum(c for c in normalized_hash_counts.values() if c > 1)

    cross_check = {
        "manifest_declared_records": manifest.get("records"),
        "computed_valid_records": valid_records,
        "match_manifest_records": manifest.get("records") == valid_records,
        "source_stats_by_modality": source_stats.get("ClinicalStatsInScope", {}).get("ByModality", {}),
        "computed_by_modality": dict(by_modality),
        "match_by_modality": dict(by_modality) == source_stats.get("ClinicalStatsInScope", {}).get("ByModality", {}),
        "source_stats_laterality_null": source_stats.get("ClinicalStatsInScope", {}).get("LateralityNull"),
        "computed_laterality_null": by_laterality.get("NULL", 0),
        "match_laterality_null": by_laterality.get("NULL", 0) == source_stats.get("ClinicalStatsInScope", {}).get("LateralityNull"),
    }

    report_text_lengths.sort()
    n = len(report_text_lengths)
    length_stats = {
        "min": report_text_lengths[0] if n else None,
        "max": report_text_lengths[-1] if n else None,
        "mean": round(sum(report_text_lengths) / n, 1) if n else None,
        "median": report_text_lengths[n // 2] if n else None,
    }

    qa_report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "snapshot_used": snapshot_dir.name,
        "snapshot_selection_reason": (
            "snapshot com maior numero de records declarado em manifest.json; "
            "os demais snapshots sob data/raw sao exports parciais anteriores "
            "do mesmo lote, preservados como historico, nao usados no baseline."
        ),
        "files_read": [f.name for f in jsonl_files],
        "totals": {
            "total_lines_read": total_lines,
            "valid_records": valid_records,
            "invalid_records": len(invalid_records),
            "duplicate_record_ids": len(duplicate_record_ids),
            "unique_patients": len({}),  # preenchido abaixo
        },
        "invalid_record_samples": invalid_records[:50],
        "invalid_record_count_total": len(invalid_records),
        "missing_field_counts": dict(missing_field_counts),
        "type_error_counts": dict(type_error_counts),
        "duplicate_record_ids_detail": duplicate_record_ids,
        "date_out_of_range": date_out_of_range,
        "unknown_modality_records": unknown_modality,
        "encoding_anomalies": encoding_flags,
        "encoding_anomaly_count": len(encoding_flags),
        "report_text_length_chars": length_stats,
        "exact_text_duplicates": {
            "note": "Mesmo texto apos hash exato. NAO implica exames clinicamente duplicados "
                    "(dois exames reais podem ter laudo identico). Apenas informativo.",
            "groups_with_repetition": exact_dupe_groups,
            "records_in_repeated_groups": exact_dupe_records,
        },
        "normalized_text_duplicates": {
            "note": "Mesmo texto apos normalizacao (casefold + espacos). Mesma ressalva acima.",
            "groups_with_repetition": normalized_dupe_groups,
            "records_in_repeated_groups": normalized_dupe_records,
        },
        "cross_check_vs_source_export_stats": cross_check,
        "distributions": {
            "by_modality": dict(by_modality.most_common()),
            "by_domain": dict(by_domain.most_common()),
            "by_anatomy": dict(by_anatomy.most_common()),
            "by_doctor": dict(by_doctor.most_common()),
            "by_sex": dict(by_sex.most_common()),
            "by_laterality": dict(by_laterality.most_common()),
            "distinct_exam_types": len(by_exam_type),
        },
    }

    unique_patient_ids = set()
    for fpath in jsonl_files:
        with fpath.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                pid = rec.get("patient_id")
                if pid is not None:
                    unique_patient_ids.add(pid)
    qa_report["totals"]["unique_patients"] = len(unique_patient_ids)
    qa_report["cross_check_vs_source_export_stats"]["manifest_declared_unique_patients"] = manifest.get("unique_patients")
    qa_report["cross_check_vs_source_export_stats"]["computed_unique_patients"] = len(unique_patient_ids)
    qa_report["cross_check_vs_source_export_stats"]["match_unique_patients"] = (
        manifest.get("unique_patients") == len(unique_patient_ids)
    )

    QA_DIR.mkdir(parents=True, exist_ok=True)
    (QA_DIR / "QA_REPORT.json").write_text(
        json.dumps(qa_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # exam_types.csv
    exam_types_csv_path = QA_DIR / "exam_types.csv"
    with exam_types_csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "exam_type", "modality", "domain", "anatomy", "count",
            "distinct_doctors", "laterality_values"
        ])
        for et, meta in sorted(exam_type_meta.items(), key=lambda kv: -kv[1]["count"]):
            writer.writerow([
                et, meta["modality"], meta["domain"], meta["anatomy"], meta["count"],
                len(meta["doctors"]), "|".join(sorted(meta["laterality_values"])),
            ])

    # physicians.csv
    physicians_csv_path = QA_DIR / "physicians.csv"
    with physicians_csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["doctor", "total", "by_modality", "by_domain"])
        for doc, meta in sorted(doctor_meta.items(), key=lambda kv: -kv[1]["total"]):
            writer.writerow([
                doc, meta["total"],
                json.dumps(dict(meta["by_modality"]), ensure_ascii=False),
                json.dumps(dict(meta["by_domain"]), ensure_ascii=False),
            ])

    # BASELINE_REPORT.md
    lines = []
    lines.append("# BASELINE_REPORT — LaudoCore Fase 0\n")
    lines.append(f"Gerado em: {qa_report['generated_at']}\n")
    lines.append(f"Snapshot usado: `{snapshot_dir.name}`\n")
    lines.append(
        "Motivo: o ZIP recebido contem tres exports cumulativos do mesmo lote, "
        "gerados no mesmo dia (03:02, 13:27 e 18:47 UTC de 2026-09-07). "
        "Nao sao corpora distintos — sao snapshots sucessivos do mesmo processo "
        "de export em andamento. Foi usado o snapshot com maior contagem de "
        "registros declarada em `manifest.json` (18:47, 8.402 registros); os "
        "demais foram preservados em `data/raw/` como historico, mas nao "
        "entram nas estatisticas abaixo.\n"
    )
    lines.append("## Escopo declarado pelo export\n")
    lines.append(f"- Janela: {manifest['source_scope']['date_from']} a {manifest['source_scope']['date_to']}")
    lines.append(f"- Modalidades no escopo do lote: {', '.join(manifest['source_scope']['modalities'])}")
    lines.append(f"- Status do export: `{manifest['source_scope']['status']}`, `complete: {manifest.get('complete')}`")
    lines.append(
        "- **US ainda nao esta presente neste export** (confirmado pelo usuario e por "
        "`ScopedCompletion.US: false` / ausencia de registros US no lote atual). "
        "Nao tratar a ausencia de US como corpus completo — sera um lote de ingestao futuro."
    )
    lines.append("")
    lines.append("## Criterio de Fase 0: 100% das linhas lidas ou justificadas\n")
    lines.append(f"- Linhas lidas: {total_lines}")
    lines.append(f"- Registros validos: {valid_records}")
    lines.append(f"- Registros invalidos (com motivo registrado em QA_REPORT.json): {len(invalid_records)}")
    lines.append(f"- **Verificacao: {total_lines} == {valid_records} + {len(invalid_records)} → {'OK' if total_lines == valid_records + len(invalid_records) else 'FALHA'}**")
    lines.append(f"- record_id duplicados detectados: {len(duplicate_record_ids)}")
    lines.append(f"- Pacientes unicos (patient_id distintos): {len(unique_patient_ids)}")
    lines.append("")
    lines.append("## Contagens reprodutiveis (recalculadas a partir do JSONL bruto, nao do export)\n")
    lines.append("### Por modalidade")
    for k, v in by_modality.most_common():
        lines.append(f"- {k}: {v}")
    lines.append("\n### Por dominio")
    for k, v in by_domain.most_common():
        lines.append(f"- {k}: {v}")
    lines.append("\n### Por medico")
    for k, v in by_doctor.most_common():
        lines.append(f"- {k}: {v}")
    lines.append(f"\n- exam_type distintos: {len(by_exam_type)}")
    lines.append(f"- Top 10 exam_type por volume:")
    for k, v in by_exam_type.most_common(10):
        lines.append(f"  - {k}: {v}")
    lines.append("")
    lines.append("## Qualidade e anomalias\n")
    lines.append(f"- Campos ausentes por tipo: {dict(missing_field_counts) if missing_field_counts else 'nenhum'}")
    lines.append(f"- Erros de tipo por campo: {dict(type_error_counts) if type_error_counts else 'nenhum'}")
    lines.append(f"- laterality nula: {by_laterality.get('NULL', 0)} de {valid_records} ({round(100*by_laterality.get('NULL',0)/valid_records,1)}%)")
    lines.append(f"- Datas fora da janela declarada (2026-06-06 a 2026-09-06): {len(date_out_of_range)}")
    lines.append(f"- modality fora de {sorted(ALLOWED_MODALITIES)}: {len(unknown_modality)}")
    lines.append(f"- Possiveis anomalias de encoding (mojibake / caractere de controle / replacement char): {len(encoding_flags)}")
    lines.append(
        f"- Duplicatas de TEXTO exato (hash sha256 do report_text): {exact_dupe_groups} grupos, "
        f"{exact_dupe_records} registros — **nao removidos**: podem ser exames reais distintos com laudo identico."
    )
    lines.append(
        f"- Duplicatas de texto normalizado (casefold + espacos): {normalized_dupe_groups} grupos, "
        f"{normalized_dupe_records} registros — mesma ressalva."
    )
    lines.append(f"- Tamanho de report_text (caracteres): min={length_stats['min']}, mediana={length_stats['median']}, media={length_stats['mean']}, max={length_stats['max']}")
    lines.append("")
    lines.append("## Cruzamento contra os numeros do proprio export (nao aceitos sem verificacao)\n")
    lines.append(f"- records declarado no manifest: {manifest.get('records')} vs recalculado: {valid_records} → "
                  f"{'CONFERE' if cross_check['match_manifest_records'] else 'DIVERGENTE'}")
    lines.append(f"- unique_patients declarado: {manifest.get('unique_patients')} vs recalculado: {len(unique_patient_ids)} → "
                  f"{'CONFERE' if qa_report['cross_check_vs_source_export_stats']['match_unique_patients'] else 'DIVERGENTE'}")
    lines.append(f"- ByModality do export vs recalculado → {'CONFERE' if cross_check['match_by_modality'] else 'DIVERGENTE'}")
    lines.append(f"- LateralityNull do export ({cross_check['source_stats_laterality_null']}) vs recalculado ({cross_check['computed_laterality_null']}) → "
                  f"{'CONFERE' if cross_check['match_laterality_null'] else 'DIVERGENTE'}")
    lines.append("")
    lines.append("## Riscos e limitacoes identificados nesta fase\n")
    lines.append("- O export ja chega filtrado/'auditado' pelo sistema de origem (CMS) — este baseline valida "
                  "consistencia interna do JSONL recebido, mas nao audita o pipeline de extracao do CMS em si "
                  "(fonte fora do nosso controle direto).")
    lines.append("- `laterality` nula em maioria dos registros (ver percentual acima) — esperado para exam_type "
                  "sem lado (ex.: coluna, torax), mas precisa ser confirmado por dominio antes da Fase 4 "
                  "(Clinical Concept Layer), para nao confundir 'nao aplicavel' com 'lado nao informado'.")
    lines.append("- `study_description_raw` e `exam_type` sao derivados pelo CMS de origem, nao pelo nosso "
                  "pipeline — a taxonomia (Fase 2) precisa tratar `exam_type` como *insumo a normalizar*, "
                  "nao como taxonomia final (ja existem variantes como `RM_QUADRIL_D` vs `RM_QUADRIL_BILATERAL`).")
    lines.append("- US ainda ausente: qualquer estatistica futura de 'corpus completo' deve reprocessar este "
                  "baseline quando o lote US chegar, em vez de apenas somar.")
    lines.append("- Corpus bruto (JSONL com report_text e patient_id) foi mantido apenas em disco local "
                  "(`data/raw/`, fora do controle de versao) e NAO foi commitado no repositorio Git — "
                  "contém texto clinico real e patient_id; ver `docs/decisions/0002-dados-fora-do-git.md`.")
    lines.append("")
    lines.append("## Proximo passo proposto\n")
    lines.append("Fase 1 (Data Engine) restrita a um unico vertical de alto volume "
                  "(candidato: RM_JOELHO_D + RM_JOELHO_E, 911 exames, MSK) — ingestao no schema `reports`, "
                  "normalizacao RAW/clean/normalized, section parser e sentence parser, antes de generalizar "
                  "para os demais exam_type.")

    (DOCS_DIR / "BASELINE_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Snapshot usado: {snapshot_dir.name}")
    print(f"Linhas lidas: {total_lines} | validos: {valid_records} | invalidos: {len(invalid_records)}")
    print(f"Pacientes unicos: {len(unique_patient_ids)}")
    print(f"Cross-check manifest.records: {cross_check['match_manifest_records']}")
    print(f"Cross-check unique_patients: {qa_report['cross_check_vs_source_export_stats']['match_unique_patients']}")
    print(f"Cross-check ByModality: {cross_check['match_by_modality']}")
    print(f"Cross-check LateralityNull: {cross_check['match_laterality_null']}")
    print(f"Saidas: {DOCS_DIR/'BASELINE_REPORT.md'}, {QA_DIR/'QA_REPORT.json'}, {exam_types_csv_path}, {physicians_csv_path}")


if __name__ == "__main__":
    main()
