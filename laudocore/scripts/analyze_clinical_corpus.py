#!/usr/bin/env python3
"""Fases 4C+4D — perfis, relacoes, associacoes, corpo x impressao,
estilo por medico e longitudinal, sobre a camada universal.

Gera os artefatos da secao 18 do PROMPT MESTRE V2 a partir de
clinical_concepts_universal. Nenhum numero aqui e' conhecimento
clinico: sao padroes DOCUMENTADOS neste corpus, com denominador,
tamanho de efeito, limitacao e status de validacao.

Controles de viesestruturais aplicados (secao 10):
  - 1.274 laudos tem texto EXATAMENTE duplicado (512 grupos). Contar
    associacao sobre eles infla coocorrencia sem evidencia nova: as
    associacoes sao calculadas sobre laudos deduplicados por hash, e a
    versao bruta e' reportada junto para a diferenca ficar visivel.
  - Unidade de analise explicita (laudo e paciente), nunca misturada.
  - Estabilidade entre medicos reportada por par: uma associacao que so
    aparece num medico e' habito autoral ate prova em contrario.
  - Correcao de multiplas comparacoes (Benjamini-Hochberg) obrigatoria.

Uso:
    python3 scripts/analyze_clinical_corpus.py
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

from backend.analysis.stats import association, benjamini_hochberg  # noqa: E402

DB_PATH = ROOT / "data" / "processed" / "laudocore.db"
ARTIFACTS = ROOT / "data" / "derived" / "artifacts"

MIN_REPORTS_FOR_ASSOCIATION = 25   # achado precisa aparecer em N laudos
MIN_SUPPORT = 10                   # co-ocorrencia minima para nao ser low_support
MIN_REPORTS_PER_DOCTOR = 50        # para avaliar estabilidade autoral
LOW_SAMPLE_EXAM = 20


def load(conn: sqlite3.Connection):
    reports = {
        r[0]: {"exam_type": r[1], "modality": r[2], "domain": r[3], "doctor": r[4],
               "patient_id": r[5], "exact_hash": r[6], "exam_datetime": r[7],
               "anatomy": r[8], "laterality": r[9]}
        for r in conn.execute(
            """SELECT id, exam_type, modality, domain, doctor, patient_id,
                      exact_hash, exam_datetime, anatomy, laterality FROM reports""")
    }
    # Linhas de legenda/citacao bibliografica nao descrevem o paciente
    # ('Tipo de Hiperplasia ( Wasserman et al )', 'Valores de referencia').
    # Sem este filtro elas viram 'achado' e produzem associacao perfeita
    # espuria — viés de template que a secao 10 manda controlar.
    concepts = conn.execute("""
        SELECT cu.report_id, cu.section_type, cu.structure, cu.finding, cu.status,
               cu.certainty, cu.severity, cu.laterality, cu.laterality_source,
               cu.temporal_status, cu.postoperative_context, cu.doctor,
               cu.exam_type, cu.source_span
        FROM clinical_concepts_universal cu
        JOIN sentences s ON cu.sentence_id = s.id
        WHERE s.text_normalized NOT LIKE '%et al%'
          AND s.text_normalized NOT LIKE '%valores de referencia%'
          AND s.text_normalized NOT LIKE '%referencia:%'
          AND s.text_normalized NOT LIKE '%escore total entre%'
    """).fetchall()
    return reports, concepts


def dedupe_report_ids(reports: dict) -> set[int]:
    """Um laudo por texto exatamente identico. O primeiro (menor id)
    representa o grupo — os demais nao trazem evidencia nova."""
    seen: dict[str, int] = {}
    for rid, meta in sorted(reports.items()):
        seen.setdefault(meta["exact_hash"], rid)
    return set(seen.values())


# ---------------------------------------------------------------- 4C
def exam_type_profiles(reports, concepts, out: Path) -> None:
    by_exam = defaultdict(lambda: {
        "reports": 0, "patients": set(), "doctors": Counter(),
        "findings_present": Counter(), "findings_absent": Counter(),
        "structures_normal": Counter(), "structures": Counter(),
        "severity": Counter(), "certainty": Counter(),
        "temporality": Counter(), "postop": Counter(),
        "impression_findings": Counter(), "concepts": 0,
    })
    for rid, meta in reports.items():
        p = by_exam[meta["exam_type"]]
        p["reports"] += 1
        p["patients"].add(meta["patient_id"])
        p["doctors"][meta["doctor"]] += 1

    for (rid, section_type, structure, finding, status, certainty, severity,
         _lat, _lsrc, temporal, postop, _doc, exam_type, _span) in concepts:
        p = by_exam[exam_type]
        p["concepts"] += 1
        if structure:
            p["structures"][structure] += 1
        if finding and status == "present":
            p["findings_present"][finding] += 1
            if section_type == "impression":
                p["impression_findings"][finding] += 1
        elif finding and status == "absent":
            p["findings_absent"][finding] += 1
        elif status == "normal" and structure:
            p["structures_normal"][structure] += 1
        if severity:
            p["severity"][severity] += 1
        p["certainty"][certainty] += 1
        if temporal:
            p["temporality"][temporal] += 1
        if postop:
            p["postop"][postop] += 1

    profiles = {}
    for exam_type, p in by_exam.items():
        low = p["reports"] < LOW_SAMPLE_EXAM
        profiles[exam_type] = {
            "reports": p["reports"],
            "patients": len(p["patients"]),
            "doctors": dict(p["doctors"].most_common()),
            "concepts": p["concepts"],
            "top_structures_evaluated": p["structures"].most_common(20),
            "top_findings_present": p["findings_present"].most_common(20),
            "top_findings_explicitly_absent": p["findings_absent"].most_common(15),
            "top_structures_explicitly_normal": p["structures_normal"].most_common(15),
            "severity_distribution": dict(p["severity"].most_common()),
            "certainty_distribution": dict(p["certainty"].most_common()),
            "temporality_distribution": dict(p["temporality"].most_common()),
            "postoperative_context": dict(p["postop"].most_common()),
            "findings_reaching_impression": p["impression_findings"].most_common(15),
            "sample_status": "low_sample" if low else "sufficient_for_description",
            "generalization_allowed": (
                "nao — amostra insuficiente; descrever apenas" if low else
                "descricao do corpus; NAO e' conhecimento clinico validado"),
            "validation_status": "extraction_candidate",
        }
    out.write_text(json.dumps(profiles, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  EXAM_TYPE_CLINICAL_PROFILES.json — {len(profiles)} tipos")


def normality_candidates(concepts, reports, out: Path) -> None:
    """Frases de normalidade explicita por estrutura e tipo de exame.
    Candidatas — nunca promovidas a template sem revisao medica."""
    rows = defaultdict(lambda: {"n": 0, "doctors": Counter(), "spans": Counter()})
    for (_rid, _st, structure, finding, status, _cert, _sev, _lat, _ls,
         _tmp, _po, doctor, exam_type, span) in concepts:
        if status != "normal" or not structure:
            continue
        key = (exam_type, structure)
        rows[key]["n"] += 1
        rows[key]["doctors"][doctor] += 1
        rows[key]["spans"][span.strip()] += 1

    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["exam_type", "structure", "n_explicit_normality",
                     "n_doctors", "doctors", "most_common_span",
                     "single_author_evidence", "validation_status"])
        for (exam_type, structure), v in sorted(rows.items(), key=lambda kv: -kv[1]["n"]):
            w.writerow([
                exam_type, structure, v["n"], len(v["doctors"]),
                "|".join(sorted(v["doctors"])),
                v["spans"].most_common(1)[0][0] if v["spans"] else "",
                "sim" if len(v["doctors"]) == 1 else "nao",
                "extraction_candidate",
            ])
    print(f"  NORMALITY_CANDIDATES.csv — {len(rows)} pares (exame, estrutura)")


# ---------------------------------------------------------------- 4D
def associations(reports, concepts, out_csv: Path, out_jsonl: Path) -> None:
    """Coocorrencia entre achados PRESENTES, no nivel LAUDO, com
    denominador restrito ao mesmo tipo de exame — comparar achado de
    joelho com achado de torax nao tem denominador comum e produziria
    associacao espuria por estrutura do corpus."""
    keep = dedupe_report_ids(reports)

    findings_by_report_all = defaultdict(set)
    findings_by_report = defaultdict(set)
    for (rid, _st, _structure, finding, status, _cert, _sev, _lat, _ls,
         _tmp, _po, _doc, _et, _span) in concepts:
        if not finding or status != "present":
            continue
        findings_by_report_all[rid].add(finding)
        if rid in keep:
            findings_by_report[rid].add(finding)

    # agrupa por exam_type (denominador elegivel)
    reports_by_exam = defaultdict(list)
    for rid in keep:
        reports_by_exam[reports[rid]["exam_type"]].append(rid)

    results = []
    for exam_type, rids in reports_by_exam.items():
        if len(rids) < MIN_REPORTS_FOR_ASSOCIATION:
            continue
        counts = Counter()
        for rid in rids:
            for f in findings_by_report.get(rid, ()):
                counts[f] += 1
        frequent = [f for f, n in counts.items() if n >= MIN_REPORTS_FOR_ASSOCIATION]
        if len(frequent) < 2:
            continue
        frequent.sort()
        n_total = len(rids)
        for i, fa in enumerate(frequent):
            for fb in frequent[i + 1:]:
                a = b = c = d = 0
                pa_patients = set()
                pa_doctors = Counter()
                for rid in rids:
                    fs = findings_by_report.get(rid, ())
                    has_a, has_b = fa in fs, fb in fs
                    if has_a and has_b:
                        a += 1
                        pa_patients.add(reports[rid]["patient_id"])
                        pa_doctors[reports[rid]["doctor"]] += 1
                    elif has_a:
                        b += 1
                    elif has_b:
                        c += 1
                    else:
                        d += 1
                if a == 0:
                    continue
                res = association(a, b, c, d, min_support=MIN_SUPPORT)

                # contagem BRUTA (sem dedup) para expor o efeito do
                # texto duplicado sobre a coocorrencia
                a_raw = sum(1 for rid, fs in findings_by_report_all.items()
                            if reports[rid]["exam_type"] == exam_type
                            and fa in fs and fb in fs)

                results.append({
                    "exam_type": exam_type, "antecedent_concept": fa,
                    "consequent_concept": fb, "unit_of_analysis": "report",
                    "support_n": a, "support_n_without_dedup": a_raw,
                    "eligible_denominator": n_total,
                    "n_patients": len(pa_patients),
                    "n_doctors": len(pa_doctors),
                    "doctors": "|".join(sorted(pa_doctors)),
                    "p_b_given_a": round(res.p_b_given_a, 4),
                    "p_b_without_a": round(res.p_b_without_a, 4),
                    "absolute_difference": round(res.absolute_difference, 4),
                    "prevalence_ratio": round(res.prevalence_ratio, 3),
                    "pr_ci_low": round(res.prevalence_ratio_ci[0], 3),
                    "pr_ci_high": round(res.prevalence_ratio_ci[1], 3),
                    "odds_ratio": round(res.odds_ratio, 3),
                    "or_ci_low": round(res.odds_ratio_ci[0], 3),
                    "or_ci_high": round(res.odds_ratio_ci[1], 3),
                    "lift": round(res.lift, 3),
                    "p_a_given_b": round(res.p_a_given_b, 4),
                    "mutually_locked_artifact": res.mutually_locked,
                    "p_value": res.p_value,
                    "low_support_flag": res.low_support,
                    "single_author_evidence": len(pa_doctors) == 1,
                    "_res": res,
                })

    qs = benjamini_hochberg([r["p_value"] for r in results])
    for r, q in zip(results, qs):
        r["q_value"] = q
        r["_res"].q_value = q
        r["interpretation_allowed"] = r["_res"].interpretation_allowed()
        r["relation_type"] = ("structural_or_template_artifact"
                               if r["mutually_locked_artifact"] else "co_occurs_with")
        r["validation_status"] = "corpus_only"
        del r["_res"]

    results.sort(key=lambda r: (r["q_value"], -r["support_n"]))

    fields = [k for k in results[0]] if results else []
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(results)
    with out_jsonl.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    sig = sum(1 for r in results if r["q_value"] <= 0.05
              and not r["mutually_locked_artifact"])
    locked = sum(1 for r in results if r["mutually_locked_artifact"])
    print(f"  ASSOCIATION_STATISTICS.csv — {len(results)} pares testados, "
           f"{sig} com q<=0.05 (excluidos {locked} artefatos estruturais)")
    print(f"  CLINICAL_RELATIONS.jsonl — {len(results)} relacoes co_occurs_with")


def body_vs_impression(reports, concepts, out: Path) -> None:
    """Achado no corpo x presenca na impressao. Padrao do corpus — NAO
    e' regra clinica: um achado nao levado a impressao pode ser decisao
    correta do medico, nao omissao."""
    body = defaultdict(set)
    impression = defaultdict(set)
    for (rid, section_type, _structure, finding, status, _cert, _sev, _lat,
         _ls, _tmp, _po, _doc, _et, _span) in concepts:
        if not finding or status != "present":
            continue
        (impression if section_type == "impression" else body)[rid].add(finding)

    stats = defaultdict(lambda: {"in_body": 0, "reached": 0, "impression_only": 0,
                                  "doctors": Counter(), "exam_types": Counter()})
    for rid, meta in reports.items():
        b, i = body.get(rid, set()), impression.get(rid, set())
        for f in b:
            s = stats[f]
            s["in_body"] += 1
            s["doctors"][meta["doctor"]] += 1
            s["exam_types"][meta["exam_type"]] += 1
            if f in i:
                s["reached"] += 1
        for f in i - b:
            stats[f]["impression_only"] += 1

    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["finding", "n_reports_with_finding_in_body",
                     "n_reached_impression", "pct_reached_impression",
                     "n_impression_without_body_support", "n_doctors",
                     "top_exam_type", "note"])
        for f, s in sorted(stats.items(), key=lambda kv: -kv[1]["in_body"]):
            if s["in_body"] < 10 and s["impression_only"] < 10:
                continue
            pct = 100 * s["reached"] / s["in_body"] if s["in_body"] else 0.0
            note = ("achado aparece na impressao sem suporte no corpo — "
                     "verificar" if s["impression_only"] > s["in_body"] * 0.2 else "")
            w.writerow([f, s["in_body"], s["reached"], f"{pct:.1f}",
                         s["impression_only"], len(s["doctors"]),
                         s["exam_types"].most_common(1)[0][0] if s["exam_types"] else "",
                         note])
    print(f"  CONCLUSION_MAPPINGS.csv — {len(stats)} achados")


# ------------------------------------------------------- perfis medicos
def physician_profiles(conn, reports, concepts, out_json: Path,
                        out_cmp: Path, out_phrases: Path) -> None:
    prof = defaultdict(lambda: {
        "reports": 0, "exam_types": Counter(), "sections": Counter(),
        "findings": Counter(), "normality": Counter(), "negation": 0,
        "hedged": 0, "concepts": 0, "severity": Counter(),
        "measurements": 0, "impression_reports": 0,
    })
    for rid, meta in reports.items():
        p = prof[meta["doctor"]]
        p["reports"] += 1
        p["exam_types"][meta["exam_type"]] += 1

    for (rid, section_type, structure, finding, status, certainty, severity,
         _lat, _ls, _tmp, _po, doctor, _et, span) in concepts:
        p = prof[doctor]
        p["concepts"] += 1
        p["sections"][section_type] += 1
        if finding and status == "present":
            p["findings"][finding] += 1
        if status == "absent":
            p["negation"] += 1
        if status == "normal" and structure:
            p["normality"][structure] += 1
        if certainty != "definite":
            p["hedged"] += 1
        if severity:
            p["severity"][severity] += 1

    for doctor, n in conn.execute("""
        SELECT r.doctor, COUNT(DISTINCT r.id) FROM reports r
        JOIN report_sections rs ON rs.report_id = r.id
        WHERE rs.section_type='impression' GROUP BY r.doctor"""):
        prof[doctor]["impression_reports"] = n

    profiles = {}
    for doctor, p in prof.items():
        profiles[doctor] = {
            "reports": p["reports"],
            "exam_types_covered": len(p["exam_types"]),
            "top_exam_types": p["exam_types"].most_common(10),
            "concepts_per_report": round(p["concepts"] / p["reports"], 2),
            "pct_reports_with_impression": round(
                100 * p["impression_reports"] / p["reports"], 1),
            "pct_concepts_negated": round(100 * p["negation"] / p["concepts"], 1)
            if p["concepts"] else 0,
            "pct_concepts_explicit_normality": round(
                100 * sum(p["normality"].values()) / p["concepts"], 1) if p["concepts"] else 0,
            "pct_concepts_hedged": round(100 * p["hedged"] / p["concepts"], 1)
            if p["concepts"] else 0,
            "top_findings": p["findings"].most_common(15),
            "top_structures_declared_normal": p["normality"].most_common(15),
            "severity_vocabulary": dict(p["severity"].most_common()),
            "note": ("perfil descritivo do corpus; NAO representa o perfil "
                      "Jefferson, que so pode ser alimentado por correcoes "
                      "aprovadas pelo usuario"),
        }
    out_json.write_text(json.dumps(profiles, ensure_ascii=False, indent=1), encoding="utf-8")

    with out_cmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["doctor", "reports", "exam_types_covered", "concepts_per_report",
                     "pct_with_impression", "pct_negated", "pct_explicit_normality",
                     "pct_hedged"])
        for d, v in sorted(profiles.items(), key=lambda kv: -kv[1]["reports"]):
            w.writerow([d, v["reports"], v["exam_types_covered"],
                         v["concepts_per_report"], v["pct_reports_with_impression"],
                         v["pct_concepts_negated"], v["pct_concepts_explicit_normality"],
                         v["pct_concepts_hedged"]])

    # preferencia de frase: mesma combinacao (exam_type, finding), quem
    # usa qual formulacao
    spans = defaultdict(lambda: defaultdict(Counter))
    for (_rid, _st, _structure, finding, status, _cert, _sev, _lat, _ls,
         _tmp, _po, doctor, exam_type, span) in concepts:
        if finding and status == "present":
            spans[(exam_type, finding)][doctor][span.strip()] += 1
    with out_phrases.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["exam_type", "finding", "doctor", "n", "preferred_span",
                     "n_distinct_spans", "shared_with_other_doctors"])
        for (exam_type, finding), by_doc in spans.items():
            if sum(sum(c.values()) for c in by_doc.values()) < 20:
                continue
            for doctor, counter in by_doc.items():
                top, n = counter.most_common(1)[0]
                shared = sum(1 for other, c in by_doc.items()
                              if other != doctor and top in c)
                w.writerow([exam_type, finding, doctor, sum(counter.values()), top,
                             len(counter), shared])
    print(f"  PHYSICIAN_STYLE_PROFILES.json / _COMPARISON.csv / _PHRASE_PREFERENCES.csv "
           f"— {len(profiles)} medicos")


def longitudinal(reports, concepts, out: Path) -> None:
    """Pacientes com mais de um exame do MESMO tipo. Nao infere
    evolucao clinica: mede persistencia/aparecimento TEXTUAL do achado,
    separando troca de medico (que muda o estilo, nao o paciente)."""
    by_patient_exam = defaultdict(list)
    for rid, meta in reports.items():
        by_patient_exam[(meta["patient_id"], meta["exam_type"])].append(rid)

    findings_by_report = defaultdict(set)
    for (rid, _st, _structure, finding, status, _c, _s, _l, _ls, _t, _p,
         _d, _e, _span) in concepts:
        if finding and status == "present":
            findings_by_report[rid].add(finding)

    rows = []
    for (_patient, exam_type), rids in by_patient_exam.items():
        if len(rids) < 2:
            continue
        rids_sorted = sorted(rids)
        first, last = rids_sorted[0], rids_sorted[-1]
        f_first = findings_by_report.get(first, set())
        f_last = findings_by_report.get(last, set())
        same_doctor = reports[first]["doctor"] == reports[last]["doctor"]
        rows.append({
            "exam_type": exam_type,
            "n_exams": len(rids),
            "findings_first": len(f_first),
            "findings_last": len(f_last),
            "persisted": len(f_first & f_last),
            "new_in_last": len(f_last - f_first),
            "absent_in_last": len(f_first - f_last),
            "same_doctor": same_doctor,
        })

    agg = defaultdict(lambda: {"pairs": 0, "persisted": 0, "new": 0, "gone": 0,
                                "same_doctor_pairs": 0})
    for r in rows:
        a = agg[r["exam_type"]]
        a["pairs"] += 1
        a["persisted"] += r["persisted"]
        a["new"] += r["new_in_last"]
        a["gone"] += r["absent_in_last"]
        a["same_doctor_pairs"] += int(r["same_doctor"])

    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["exam_type", "patients_with_repeat_exam", "findings_persisted",
                     "findings_new_in_later_exam", "findings_absent_in_later_exam",
                     "pct_pairs_same_doctor", "caveat"])
        for exam_type, a in sorted(agg.items(), key=lambda kv: -kv[1]["pairs"]):
            w.writerow([
                exam_type, a["pairs"], a["persisted"], a["new"], a["gone"],
                f"{100*a['same_doctor_pairs']/a['pairs']:.0f}",
                ("desaparecimento textual NAO significa resolucao clinica; "
                  "pode ser estilo, omissao ou troca de medico"),
            ])
    print(f"  LONGITUDINAL_PATTERNS.csv — {len(agg)} tipos com exame repetido "
           f"({len(rows)} pares paciente-exame)")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    reports, concepts = load(conn)
    print(f"Carregado: {len(reports)} laudos, {len(concepts)} conceitos\n")

    print("[4C] Perfis por tipo de exame e normalidade...")
    exam_type_profiles(reports, concepts, ARTIFACTS / "EXAM_TYPE_CLINICAL_PROFILES.json")
    normality_candidates(concepts, reports, ARTIFACTS / "NORMALITY_CANDIDATES.csv")

    print("\n[4D] Relacoes, associacoes e corpo x impressao...")
    associations(reports, concepts, ARTIFACTS / "ASSOCIATION_STATISTICS.csv",
                  ARTIFACTS / "CLINICAL_RELATIONS.jsonl")
    body_vs_impression(reports, concepts, ARTIFACTS / "CONCLUSION_MAPPINGS.csv")

    print("\n[perfis] Estilo por medico e longitudinal...")
    physician_profiles(conn, reports, concepts,
                        ARTIFACTS / "PHYSICIAN_STYLE_PROFILES.json",
                        ARTIFACTS / "PHYSICIAN_STYLE_COMPARISON.csv",
                        ARTIFACTS / "PHYSICIAN_PHRASE_PREFERENCES.csv")
    longitudinal(reports, concepts, ARTIFACTS / "LONGITUDINAL_PATTERNS.csv")

    print(f"\nArtefatos em {ARTIFACTS}")


if __name__ == "__main__":
    main()
