#!/usr/bin/env python3
"""Fases 4A+4B globais — lexico + camada de conceitos sobre TODO o corpus.

Executa, em um comando reproduzivel:
  1. minera o lexico clinico do corpus (backend/clinical/lexicon.py)
  2. persiste em clinical_lexicon + exporta CLINICAL_CONCEPT_DICTIONARY.json
  3. aplica o Clause Engine + camada de conceitos a todas as sentencas
     clinicas dos 8.402 laudos
  4. persiste em clinical_concepts_universal
  5. gera CLINICAL_COVERAGE_MATRIX.csv — uma linha por exam_type, com
     estado de validacao EXPLICITO (a especificacao proibe 'completed'
     sem dizer o nivel de validacao)
  6. gera UNMODELED_CLINICAL_TAIL.csv — o que ficou fora, quantificado

Uso:
    python3 scripts/mine_clinical_layer.py
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.clinical.lexicon import mine_lexicon, LEXICON_VERSION  # noqa: E402
from backend.clinical.concept_layer import (  # noqa: E402
    ConceptExtractor, load_lexicon_from_db, CONCEPT_LAYER_VERSION,
)
from backend.db.schema import rebuild_universal_schema  # noqa: E402

DB_PATH = ROOT / "data" / "processed" / "laudocore.db"
DERIVED = ROOT / "data" / "derived"
QA_DIR = DERIVED / "qa"
ARTIFACTS = DERIVED / "artifacts"

# Amostra minima para permitir generalizacao estatistica. Abaixo disso o
# tipo de exame e' descrito, nunca usado para inferir padrao (secao 4).
LOW_SAMPLE_THRESHOLD = 20


def build_lexicon(conn: sqlite3.Connection) -> int:
    print("[1/5] Minerando lexico do corpus...")
    entries = mine_lexicon(conn)
    cur = conn.cursor()
    for e in entries:
        cur.execute(
            """INSERT OR REPLACE INTO clinical_lexicon (
                term, term_type, method, confidence, frequency, n_exam_types,
                top_exam_type, concentration, p_after_preposition,
                p_clause_initial, p_after_finding_trigger, domains,
                validation_status, lexicon_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (e.term, e.term_type, e.method, e.confidence, e.frequency,
             e.n_exam_types, e.top_exam_type, e.concentration,
             e.p_after_preposition, e.p_clause_initial, e.p_after_finding_trigger,
             json.dumps(e.domains, ensure_ascii=False), e.validation_status,
             e.lexicon_version),
        )
    conn.commit()

    by_type = Counter(e.term_type for e in entries)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    dictionary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lexicon_version": LEXICON_VERSION,
        "validation_status": "extraction_candidate — nenhum termo validado clinicamente",
        "method_note": (
            "corpus_positional = estatistica medida no corpus; "
            "morphological = sufixo do portugues medico; "
            "model_knowledge = inferencia do modelo, pendente de revisao medica."
        ),
        "counts_by_type": dict(by_type.most_common()),
        "terms": [
            {"term": e.term, "type": e.term_type, "method": e.method,
             "confidence": e.confidence, "frequency": e.frequency,
             "n_exam_types": e.n_exam_types, "top_exam_type": e.top_exam_type,
             "concentration": round(e.concentration, 3),
             "p_after_preposition": e.p_after_preposition,
             "p_after_finding_trigger": e.p_after_finding_trigger,
             "domains": e.domains}
            for e in entries
        ],
    }
    (ARTIFACTS / "CLINICAL_CONCEPT_DICTIONARY.json").write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"      {len(entries)} termos | {dict(by_type.most_common())}")
    return len(entries)


def extract_concepts(conn: sqlite3.Connection) -> dict:
    print("[2/5] Carregando lexico utilizavel...")
    lexicon = load_lexicon_from_db(conn)
    extractor = ConceptExtractor(lexicon)
    print(f"      {len(lexicon)} termos utilizaveis na montagem")

    print("[3/5] Aplicando Clause Engine + camada de conceitos ao corpus...")
    rows = conn.execute("""
        SELECT s.id, s.report_id, s.section_id, s.text_raw,
               r.modality, r.domain, r.exam_type, r.doctor, r.laterality,
               rs.section_type
        FROM sentences s
        JOIN report_sections rs ON s.section_id = rs.id
        JOIN reports r ON s.report_id = r.id
        WHERE rs.section_type IN ('findings','impression')
    """).fetchall()

    cur = conn.cursor()
    stats = {
        "sentences_processed": 0,
        "sentences_with_concept": 0,
        "concepts": 0,
        "by_exam_type": defaultdict(lambda: {"sentences": 0, "with_concept": 0, "concepts": 0}),
        "by_status": Counter(),
        "by_certainty": Counter(),
        "structure_bound": 0,
    }

    for (sent_id, report_id, section_id, text, modality, domain,
         exam_type, doctor, laterality, section_type) in rows:
        concepts = extractor.extract(
            text, report_id=report_id, section_id=section_id, sentence_id=sent_id,
            modality=modality, domain=domain, exam_type=exam_type, doctor=doctor,
            section_type=section_type, exam_laterality=laterality,
        )
        stats["sentences_processed"] += 1
        et = stats["by_exam_type"][exam_type]
        et["sentences"] += 1
        if concepts:
            stats["sentences_with_concept"] += 1
            et["with_concept"] += 1
        for c in concepts:
            stats["concepts"] += 1
            et["concepts"] += 1
            stats["by_status"][c.status] += 1
            stats["by_certainty"][c.certainty] += 1
            if c.structure:
                stats["structure_bound"] += 1
            cur.execute(
                """INSERT INTO clinical_concepts_universal (
                    report_id, section_id, sentence_id, modality, domain, exam_type,
                    doctor, section_type, structure, finding, status, certainty,
                    severity, morphology, distribution, grade, laterality, laterality_source, measurements,
                    measurement_unit, temporal_status, comparison_status,
                    etiologic_qualifier, postoperative_context, modifiers,
                    char_start, char_end, source_span, extraction_method, rule_id,
                    engine_version, lexicon_version, layer_version, confidence,
                    validation_status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (c.report_id, c.section_id, c.sentence_id, c.modality, c.domain,
                 c.exam_type, c.doctor, c.section_type, c.structure, c.finding,
                 c.status, c.certainty, c.severity, c.morphology, c.distribution,
                 c.grade, c.laterality,
                 c.laterality_source,
                 json.dumps(c.measurements) if c.measurements else None,
                 c.measurement_unit, c.temporal_status, c.comparison_status,
                 c.etiologic_qualifier, c.postoperative_context,
                 json.dumps(c.modifiers, ensure_ascii=False) if c.modifiers else None,
                 c.char_start, c.char_end, c.source_span, c.extraction_method,
                 c.rule_id, c.engine_version, c.lexicon_version, c.layer_version,
                 c.confidence, c.validation_status),
            )
    conn.commit()
    print(f"      {stats['concepts']} conceitos em "
           f"{stats['sentences_with_concept']}/{stats['sentences_processed']} sentencas")
    return stats


def coverage_matrix(conn: sqlite3.Connection, stats: dict) -> None:
    print("[4/5] Gerando CLINICAL_COVERAGE_MATRIX.csv...")
    meta = conn.execute("""
        SELECT exam_type, modality, domain, anatomy,
               COUNT(*) AS reports,
               COUNT(DISTINCT patient_id) AS patients,
               COUNT(DISTINCT doctor) AS doctors,
               SUM(CASE WHEN laterality IS NOT NULL THEN 1 ELSE 0 END) AS with_laterality
        FROM reports GROUP BY exam_type
    """).fetchall()

    rel = {r[0]: r for r in conn.execute("""
        SELECT exam_type,
               COUNT(*) AS concepts,
               SUM(CASE WHEN structure IS NOT NULL THEN 1 ELSE 0 END) AS with_structure,
               SUM(CASE WHEN status='absent' THEN 1 ELSE 0 END) AS negated,
               SUM(CASE WHEN status='normal' THEN 1 ELSE 0 END) AS normality,
               SUM(CASE WHEN certainty<>'definite' THEN 1 ELSE 0 END) AS hedged,
               SUM(CASE WHEN laterality_source='conflict' THEN 1 ELSE 0 END) AS lat_conflict
        FROM clinical_concepts_universal GROUP BY exam_type
    """).fetchall()}

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / "CLINICAL_COVERAGE_MATRIX.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "exam_type", "modality", "domain", "anatomy", "laterality_applicable",
            "reports", "patients", "doctors", "clinical_sentences",
            "sentences_with_concept", "concept_coverage_pct", "concepts",
            "concepts_with_structure", "structure_binding_pct",
            "negated_concepts", "explicit_normality_concepts", "hedged_concepts",
            "laterality_conflicts", "validation_status", "limitations",
            "next_pending_step",
        ])
        for exam_type, modality, domain, anatomy, reports, patients, doctors, with_lat in meta:
            s = stats["by_exam_type"].get(exam_type, {"sentences": 0, "with_concept": 0, "concepts": 0})
            r = rel.get(exam_type, (exam_type, 0, 0, 0, 0, 0, 0))
            cov = 100 * s["with_concept"] / s["sentences"] if s["sentences"] else 0.0
            bind = 100 * r[2] / r[1] if r[1] else 0.0

            if s["sentences"] == 0:
                status = "blocked_missing_data"
                limitation = "nenhuma sentenca clinica extraida deste tipo"
                nxt = "revisar parsing de secoes para este tipo"
            elif reports < LOW_SAMPLE_THRESHOLD:
                status = "low_sample"
                limitation = (f"amostra insuficiente ({reports} laudos) para generalizacao "
                               "estatistica; descrito, nao generalizado")
                nxt = "descrever qualitativamente; nao derivar associacao"
            elif cov < 50:
                status = "processed_unvalidated"
                limitation = (f"cobertura de conceito baixa ({cov:.0f}%) — vocabulario do "
                               "lexico ainda nao cobre este tipo")
                nxt = "ampliar lexico para este dominio a partir da cauda nao modelada"
            else:
                status = "review_sample_pending"
                limitation = "extraido e nao revisado; nenhuma validacao clinica realizada"
                nxt = "revisao textual de amostra estratificada (Fase 4E)"

            w.writerow([
                exam_type, modality, domain, anatomy,
                "sim" if with_lat else "nao",
                reports, patients, doctors, s["sentences"], s["with_concept"],
                f"{cov:.1f}", r[1], r[2], f"{bind:.1f}", r[3], r[4], r[5], r[6],
                status, limitation, nxt,
            ])
    print(f"      {out}")


def unmodeled_tail(conn: sqlite3.Connection) -> None:
    print("[5/5] Gerando UNMODELED_CLINICAL_TAIL.csv...")
    rows = conn.execute("""
        SELECT term, frequency, n_exam_types, top_exam_type, concentration,
               p_after_preposition, p_after_finding_trigger, domains
        FROM clinical_lexicon
        WHERE term_type IN ('unclassified','unclassified_compound')
        ORDER BY frequency DESC
    """).fetchall()
    out = ARTIFACTS / "UNMODELED_CLINICAL_TAIL.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["term", "frequency", "n_exam_types", "top_exam_type",
                     "concentration", "p_after_preposition", "p_after_finding_trigger",
                     "domains", "priority", "reason_not_modeled"])
        for (term, freq, n_exams, top, conc, p_prep, p_find, domains) in rows:
            priority = "alta" if freq >= 500 else ("media" if freq >= 100 else "baixa")
            if p_prep >= 0.4:
                reason = "provavel anatomia sem nucleo conhecido no lexico"
            elif p_find >= 0.15:
                reason = "provavel achado sem sufixo morfologico reconhecido"
            elif " " in term:
                reason = "composto cujo nucleo nao foi classificado"
            else:
                reason = "termo sem sinal posicional nem morfologico suficiente"
            w.writerow([term, freq, n_exams, top, f"{conc:.2f}", p_prep, p_find,
                         domains, priority, reason])
    print(f"      {out} ({len(rows)} termos)")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    rebuild_universal_schema(conn)
    n_terms = build_lexicon(conn)
    stats = extract_concepts(conn)
    coverage_matrix(conn, stats)
    unmodeled_tail(conn)

    QA_DIR.mkdir(parents=True, exist_ok=True)
    qa = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "4A+4B global",
        "layer_version": CONCEPT_LAYER_VERSION,
        "lexicon_terms": n_terms,
        "sentences_processed": stats["sentences_processed"],
        "sentences_with_concept": stats["sentences_with_concept"],
        "shallow_coverage_pct": round(
            100 * stats["sentences_with_concept"] / stats["sentences_processed"], 1),
        "coverage_caveat": (
            "cobertura SUPERFICIAL: mede apenas se a sentenca gerou >=1 conceito. "
            "NAO e' recall clinico e nao pode ser apresentada como tal (secao 16.2 "
            "do prompt mestre). Recall por eixo exige amostra anotada."
        ),
        "concepts_total": stats["concepts"],
        "concepts_with_structure": stats["structure_bound"],
        "structure_binding_pct": round(
            100 * stats["structure_bound"] / stats["concepts"], 1) if stats["concepts"] else 0,
        "by_status": dict(stats["by_status"].most_common()),
        "by_certainty": dict(stats["by_certainty"].most_common()),
    }
    (QA_DIR / "CLINICAL_QA_REPORT.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n--- RESUMO ---")
    print(f"Conceitos: {stats['concepts']} | com estrutura ligada: "
           f"{qa['structure_binding_pct']}%")
    print(f"Cobertura superficial: {qa['shallow_coverage_pct']}% "
           f"({stats['sentences_with_concept']}/{stats['sentences_processed']} sentencas)")
    print(f"Status: {dict(stats['by_status'].most_common())}")
    print(f"Certeza: {dict(stats['by_certainty'].most_common())}")


if __name__ == "__main__":
    main()
