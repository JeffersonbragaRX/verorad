#!/usr/bin/env python3
"""Fase 4E / secao 16 — avaliacao por EIXO clinico.

Tres coisas distintas, deliberadamente separadas porque tem forca
epistemica diferente:

  A. EVAL ADVERSARIAL SINTETICO — casos construidos com gabarito
     explicito, cobrindo os eixos que o clause engine resolve
     (polaridade, escopo de negacao, certeza, lateralidade, medida,
     grau, temporalidade). Pontuado automaticamente. E' medida real de
     comportamento, mas sobre texto FABRICADO: nao mede desempenho no
     corpus.

  B. AMOSTRA ESTRATIFICADA PARA ANOTACAO MEDICA — sorteada do corpus
     real, estratificada por modalidade/dominio/exame/medico e
     enriquecida com casos dificeis. Sai como arquivo para o
     radiologista anotar. Sem ela nao existe recall clinico: a
     'cobertura' que o pipeline reporta e' superficial e NAO pode ser
     apresentada como recall (secao 16.2).

  C. Metricas de cobertura por eixo no corpus — quantos conceitos
     receberam cada atributo. E' DESCRICAO do que foi extraido, nao
     acuracia: um eixo pode ter 100% de preenchimento e estar errado.

Uso:
    python3 scripts/run_clinical_eval.py
"""

from __future__ import annotations

import json
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.clinical.clause_engine import analyze_sentence  # noqa: E402

DB_PATH = ROOT / "data" / "processed" / "laudocore.db"
ARTIFACTS = ROOT / "data" / "derived" / "artifacts"
EVAL_DIR = ROOT / "data" / "derived" / "eval"

SEED = 20260908

# ---------------------------------------------------------------- A
# Casos com gabarito. 'mention' e' a expressao cujo eixo esta sendo
# avaliado; o gabarito diz o que o motor DEVE responder para ela.
ADVERSARIAL_CASES = [
    # --- polaridade / escopo de negacao ---
    {"id": "neg01", "axis": "status", "modality_style": "RM",
     "text": "Rotura do ligamento cruzado anterior, sem lesão meniscal.",
     "mention": "Rotura", "expected": "present",
     "why": "negacao de outra estrutura na mesma sentenca"},
    {"id": "neg02", "axis": "status", "modality_style": "RM",
     "text": "Rotura do ligamento cruzado anterior, sem lesão meniscal.",
     "mention": "lesão meniscal", "expected": "absent",
     "why": "o alvo real da negacao"},
    {"id": "neg03", "axis": "status", "modality_style": "RM",
     "text": "Menisco medial sem roturas, observando-se lesão do menisco lateral.",
     "mention": "lesão do menisco lateral", "expected": "present",
     "why": "polaridade oposta por clausula"},
    {"id": "neg04", "axis": "status", "modality_style": "RM",
     "text": "Rotura parcial do supraespinal sem componente transfixante.",
     "mention": "Rotura parcial", "expected": "present",
     "why": "negacao parcial nega o qualificador, nao o achado"},
    {"id": "neg05", "axis": "status", "modality_style": "TC",
     "text": "Ausência de consolidações alveolares, notando-se nódulo pulmonar.",
     "mention": "nódulo pulmonar", "expected": "present",
     "why": "verbo de apresentacao encerra o escopo"},
    {"id": "neg06", "axis": "status", "modality_style": "RX",
     "text": "Espaços articulares preservados, sem sinais de fratura.",
     "mention": "Espaços articulares", "expected": "normal",
     "why": "normalidade explicita nao e' negacao de achado"},
    {"id": "neg07", "axis": "status", "modality_style": "RM",
     "text": "Achado sempre presente nos controles.",
     "mention": "presente", "expected": "present",
     "why": "'sempre' contem 'sem' — fronteira de palavra"},
    {"id": "neg08", "axis": "status", "modality_style": "RM",
     "text": "Nódulo abaulando os contornos, não podendo ser descartada infiltração.",
     "mention": "infiltração", "expected": "present",
     "why": "dupla negacao: incerteza, nao ausencia"},
    # --- certeza ---
    {"id": "cer01", "axis": "certainty", "modality_style": "RM",
     "text": "Nódulo abaulando os contornos, não podendo ser descartada infiltração.",
     "mention": "infiltração", "expected": "cannot_exclude", "why": "dupla negacao"},
    {"id": "cer02", "axis": "certainty", "modality_style": "RM",
     "text": "Achado sugestivo de hemangioma.",
     "mention": "hemangioma", "expected": "probable", "why": "hedge de probabilidade"},
    {"id": "cer03", "axis": "certainty", "modality_style": "TC",
     "text": "Nódulo que pode corresponder a granuloma.",
     "mention": "granuloma", "expected": "possible", "why": "hedge fraco"},
    {"id": "cer04", "axis": "certainty", "modality_style": "RX",
     "text": "Fratura do rádio distal.",
     "mention": "Fratura", "expected": "definite", "why": "sem hedge"},
    {"id": "cer05", "axis": "certainty", "modality_style": "RM",
     "text": "Nódulo possivelmente inflamatório, associado a fratura do platô tibial.",
     "mention": "fratura do platô tibial", "expected": "definite",
     "why": "incerteza nao vaza para a outra clausula"},
    {"id": "cer06", "axis": "certainty", "modality_style": "RM",
     "text": "Focos de alteração de sinal na substância branca, inespecíficos.",
     "mention": "Focos de alteração de sinal", "expected": "definite",
     "why": "'inespecifico' e' etiologia, nao certeza"},
    # --- lateralidade ---
    {"id": "lat01", "axis": "laterality", "modality_style": "RM",
     "text": "Derrame articular no joelho esquerdo.",
     "mention": "Derrame articular", "expected": "left", "why": "lado local"},
    {"id": "lat02", "axis": "laterality", "modality_style": "RM",
     "text": "Alterações degenerativas bilaterais nos quadris.",
     "mention": "Alterações degenerativas", "expected": "bilateral", "why": "bilateralidade"},
    {"id": "lat03", "axis": "laterality", "modality_style": "RM",
     "text": "Rotura do supraespinal à direita, tendinopatia à esquerda.",
     "mention": "tendinopatia", "expected": "left", "why": "dois lados na mesma sentenca"},
    # --- medida ---
    {"id": "med01", "axis": "measurement", "modality_style": "RM",
     "text": "Cisto poplíteo medindo 3,2 cm, com lesão condral de 0,8 cm no côndilo medial.",
     "mention": "Cisto poplíteo", "expected": "3.2", "why": "medida por clausula"},
    {"id": "med02", "axis": "measurement", "modality_style": "RM",
     "text": "Cisto poplíteo medindo 3,2 cm, com lesão condral de 0,8 cm no côndilo medial.",
     "mention": "lesão condral", "expected": "0.8", "why": "a outra medida"},
    {"id": "med03", "axis": "measurement", "modality_style": "RM",
     "text": "Próstata medindo 3,4 x 4,0 x 4,5 cm.",
     "mention": "Próstata", "expected": "3.4", "why": "medida tridimensional"},
    # --- grau ---
    {"id": "gra01", "axis": "grade", "modality_style": "RM",
     "text": "Condropatia femoropatelar grau II/III.",
     "mention": "Condropatia", "expected": "2_3", "why": "faixa de grau nao truncada"},
    {"id": "gra02", "axis": "grade", "modality_style": "RM",
     "text": "Condropatia patelofemoral grau III, condropatia femorotibial medial grau I.",
     "mention": "condropatia femorotibial medial", "expected": "1",
     "why": "graus diferentes por clausula"},
    # --- temporalidade / pos-operatorio ---
    {"id": "tmp01", "axis": "temporality", "modality_style": "RM",
     "text": "Alterações crônicas na inserção do tendão.",
     "mention": "Alterações", "expected": "chronic", "why": "cronicidade"},
    {"id": "pop01", "axis": "postoperative", "modality_style": "RM",
     "text": "Reconstrução do ligamento cruzado anterior, enxerto íntegro.",
     "mention": "enxerto", "expected": "graft", "why": "enxerto nao e' estrutura nativa"},
    # --- comparacao ---
    {"id": "cmp01", "axis": "comparison", "modality_style": "TC",
     "text": "Nódulo estável, com linfonodo aumentado.",
     "mention": "Nódulo", "expected": "stable", "why": "comparacao por clausula"},
    {"id": "cmp02", "axis": "comparison", "modality_style": "TC",
     "text": "Nódulo estável, com linfonodo aumentado.",
     "mention": "linfonodo", "expected": "increased", "why": "a outra comparacao"},
]


def run_adversarial() -> dict:
    by_axis = defaultdict(lambda: {"n": 0, "correct": 0, "failures": []})
    for case in ADVERSARIAL_CASES:
        text, mention = case["text"], case["mention"]
        idx = text.lower().index(mention.lower())
        start, end = idx, idx + len(mention)
        a = analyze_sentence(text)
        axis = case["axis"]

        if axis == "status":
            got = a.status_at(start, end)[0]
        elif axis == "certainty":
            got = a.certainty_at(start, end)
        elif axis == "laterality":
            got = a.laterality_at(start, end)
        elif axis == "measurement":
            ms = a.measurements_for(start, end)
            got = str(ms[0].values[0]) if ms else None
        elif axis == "grade":
            gs = a.grades_for(start, end)
            got = gs[0] if gs else None
        elif axis == "temporality":
            got = a.temporality_at(start, end)
        elif axis == "postoperative":
            got = a.postop_at(start, end)
        elif axis == "comparison":
            got = a.comparison_at(start, end)
        else:
            got = None

        slot = by_axis[axis]
        slot["n"] += 1
        if got == case["expected"]:
            slot["correct"] += 1
        else:
            slot["failures"].append({
                "id": case["id"], "text": text, "mention": mention,
                "expected": case["expected"], "got": got, "why": case["why"],
            })

    total = sum(v["n"] for v in by_axis.values())
    correct = sum(v["correct"] for v in by_axis.values())
    return {
        "cases": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "by_axis": {
            k: {"n": v["n"], "correct": v["correct"],
                "accuracy": round(v["correct"] / v["n"], 4),
                "failures": v["failures"]}
            for k, v in sorted(by_axis.items())
        },
        "caveat": ("texto FABRICADO com gabarito proprio. Mede o comportamento "
                    "do motor nos casos que ele foi projetado para resolver — "
                    "NAO e' desempenho no corpus real nem acuracia clinica."),
    }


# ---------------------------------------------------------------- B
def build_annotation_sample(conn: sqlite3.Connection, n_random: int = 120,
                             n_hard: int = 80) -> dict:
    """Amostra estratificada + enriquecida, separada POR PACIENTE para
    nao vazar o mesmo paciente entre estratos."""
    rnd = random.Random(SEED)

    rows = conn.execute("""
        SELECT s.id, s.text_raw, r.id, r.patient_id, r.modality, r.domain,
               r.exam_type, r.doctor, rs.section_type
        FROM sentences s
        JOIN report_sections rs ON s.section_id = rs.id
        JOIN reports r ON s.report_id = r.id
        WHERE rs.section_type IN ('findings','impression')
          AND LENGTH(s.text_raw) > 25
    """).fetchall()

    # estratificacao por (modalidade, dominio) — proporcional
    by_stratum = defaultdict(list)
    for row in rows:
        by_stratum[(row[4], row[5])].append(row)

    sample, used_patients = [], set()
    total = len(rows)
    for stratum, items in by_stratum.items():
        quota = max(1, round(n_random * len(items) / total))
        rnd.shuffle(items)
        taken = 0
        for row in items:
            if taken >= quota:
                break
            if row[3] in used_patients:
                continue
            used_patients.add(row[3])
            sample.append({"strategy": "stratified_random", "stratum": list(stratum),
                            "sentence_id": row[0], "text": row[1], "report_id": row[2],
                            "modality": row[4], "domain": row[5], "exam_type": row[6],
                            "doctor": row[7], "section_type": row[8]})
            taken += 1

    # enriquecimento por dificuldade — cada categoria e' um caso que ja
    # quebrou alguma versao do extrator
    hard_patterns = {
        "negacao_multipla": "%sem%",
        "incerteza": "%pode%",
        "medidas_multiplas": "%x %",
        "bilateralidade": "%bilateral%",
        "pos_operatorio": "%pós-operatório%",
        "comparacao": "%estável%",
        "grau": "%grau %",
        "coordenacao": "% e %",
    }
    per_pattern = max(1, n_hard // len(hard_patterns))
    for label, like in hard_patterns.items():
        got = conn.execute("""
            SELECT s.id, s.text_raw, r.id, r.patient_id, r.modality, r.domain,
                   r.exam_type, r.doctor, rs.section_type
            FROM sentences s
            JOIN report_sections rs ON s.section_id = rs.id
            JOIN reports r ON s.report_id = r.id
            WHERE rs.section_type IN ('findings','impression')
              AND s.text_raw LIKE ? AND LENGTH(s.text_raw) > 60
            ORDER BY RANDOM() LIMIT ?
        """, (like, per_pattern * 3)).fetchall()
        taken = 0
        for row in got:
            if taken >= per_pattern or row[3] in used_patients:
                continue
            used_patients.add(row[3])
            sample.append({"strategy": f"hard_case:{label}", "stratum": [row[4], row[5]],
                            "sentence_id": row[0], "text": row[1], "report_id": row[2],
                            "modality": row[4], "domain": row[5], "exam_type": row[6],
                            "doctor": row[7], "section_type": row[8]})
            taken += 1

    # saida do sistema para cada item, para o revisor comparar
    for item in sample:
        concepts = conn.execute("""
            SELECT structure, finding, status, certainty, severity, grade,
                   laterality, laterality_source, measurements, temporal_status,
                   comparison_status, etiologic_qualifier, postoperative_context,
                   source_span
            FROM clinical_concepts_universal WHERE sentence_id = ?
        """, (item["sentence_id"],)).fetchall()
        item["system_output"] = [
            {"structure": c[0], "finding": c[1], "status": c[2], "certainty": c[3],
             "severity": c[4], "grade": c[5], "laterality": c[6],
             "laterality_source": c[7], "measurements": c[8], "temporal_status": c[9],
             "comparison_status": c[10], "etiologic_qualifier": c[11],
             "postoperative_context": c[12], "span": c[13]}
            for c in concepts
        ]
        item["annotation"] = {
            axis: None for axis in
            ("structure_correct", "finding_correct", "status_correct",
             "certainty_correct", "laterality_correct", "measurement_correct",
             "grade_correct", "temporality_correct", "missing_concepts",
             "spurious_concepts", "reviewer_note")
        }
    return {"sample": sample, "used_patients": len(used_patients)}


# ---------------------------------------------------------------- C
def axis_fill_rates(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM clinical_concepts_universal").fetchone()[0]
    axes = ("structure", "finding", "severity", "morphology", "distribution",
            "grade", "laterality", "measurements", "temporal_status",
            "comparison_status", "etiologic_qualifier", "postoperative_context")
    out = {}
    for axis in axes:
        n = conn.execute(
            f"SELECT COUNT(*) FROM clinical_concepts_universal WHERE {axis} IS NOT NULL"
        ).fetchone()[0]
        out[axis] = {"filled": n, "pct": round(100 * n / total, 1) if total else 0.0}
    return {
        "concepts_total": total,
        "fill_rate_by_axis": out,
        "caveat": ("PREENCHIMENTO, nao acuracia. Um eixo com 100% de "
                    "preenchimento pode estar 100% errado — acuracia por eixo "
                    "exige a amostra anotada (bloco B)."),
    }


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print("[A] Eval adversarial sintetico (gabarito explicito)...")
    adversarial = run_adversarial()
    print(f"    {adversarial['correct']}/{adversarial['cases']} "
           f"({100*adversarial['accuracy']:.1f}%)")
    for axis, v in adversarial["by_axis"].items():
        print(f"      {axis:<16} {v['correct']}/{v['n']}")

    print("\n[B] Amostra estratificada para anotacao medica...")
    sample_data = build_annotation_sample(conn)
    sample = sample_data["sample"]
    strat = Counter(s["strategy"].split(":")[0] for s in sample)
    print(f"    {len(sample)} sentencas | {dict(strat)} | "
           f"{sample_data['used_patients']} pacientes distintos")
    # a amostra contem TEXTO REAL de laudo: fica fora do git (data/derived/eval)
    (EVAL_DIR / "EVAL_SAMPLE_FOR_ANNOTATION.json").write_text(
        json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n[C] Preenchimento por eixo no corpus...")
    fills = axis_fill_rates(conn)
    for axis, v in fills["fill_rate_by_axis"].items():
        print(f"      {axis:<24} {v['pct']:5.1f}%")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "A_adversarial_synthetic": adversarial,
        "B_annotation_sample": {
            "n_sentences": len(sample),
            "n_distinct_patients": sample_data["used_patients"],
            "by_strategy": dict(Counter(s["strategy"] for s in sample)),
            "file": "data/derived/eval/EVAL_SAMPLE_FOR_ANNOTATION.json "
                     "(fora do git — contem texto real de laudo)",
            "status": "aguardando anotacao do radiologista",
            "blocking_note": ("sem esta anotacao NAO existe recall nem precisao "
                               "clinica; qualquer numero de 'cobertura' e' superficial"),
        },
        "C_axis_fill_rates": fills,
        "what_this_report_does_not_establish": [
            "acuracia clinica de qualquer eixo no corpus real",
            "recall clinico (exige gabarito anotado por radiologista)",
            "validade das associacoes como conhecimento medico",
            "adequacao de qualquer frase a um paciente especifico",
        ],
    }
    (ARTIFACTS / "CLINICAL_EVAL_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRelatorio: {ARTIFACTS / 'CLINICAL_EVAL_REPORT.json'}")


if __name__ == "__main__":
    main()
