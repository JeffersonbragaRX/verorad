#!/usr/bin/env python3
"""Fase 6 — demonstracao e QA do Report Compiler (RM de joelho).

Nao e' um script de producao (nao ha UI ainda) — mostra o fluxo real:
o medico decide os achados (FindingRequest), o compilador so escolhe
a frase real do corpus para cada um. Gera tambem uma metrica agregada
de cobertura impressao/achados (QA_REPORT_FASE6.json, sem texto real).

Uso:
    python3 scripts/compile_report_demo.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.compiler.phrase_bank import build_phrase_bank  # noqa: E402
from backend.compiler.report_compiler import FindingRequest, compile_report  # noqa: E402

DB_PATH = ROOT / "data" / "processed" / "laudocore.db"
QA_DIR = ROOT / "data" / "derived" / "qa"


def run_demo(conn, bank) -> None:
    example_findings = [
        FindingRequest("meniscus_medial", "tear", "present", location="posterior_horn"),
        FindingRequest("meniscus_lateral", "tear", "absent"),
        FindingRequest("acl", "tear", "present", severity="complete"),
        FindingRequest("pcl", "tear", "absent"),
        FindingRequest("joint_space", "effusion", "present", severity="moderado"),
        FindingRequest("baker_cyst", "cyst", "present"),
    ]
    result = compile_report(conn, example_findings, doctor="RAFAEL", phrase_bank=bank)

    print("=== LAUDO COMPILADO (demo, achados fabricados) ===")
    print(result.render(indication_text="Dor no joelho."))
    print()
    print("Não resolvidos (sem frase real no corpus para essa combinação):")
    for u in result.unresolved:
        print(" -", u)
    print("Avisos do auditor:")
    for w in result.warnings:
        print(" -", w)


def compute_coverage_qa(conn) -> dict:
    rows = conn.execute(
        "SELECT DISTINCT structure, finding, status, severity, location, section_type "
        "FROM clinical_concepts"
    ).fetchall()

    findings_keys = {r[:5] for r in rows if r[5] == "findings"}
    impression_keys = {r[:5] for r in rows if r[5] == "impression"}

    present_findings_keys = {k for k in findings_keys if k[2] == "present"}
    with_impression_phrase = sum(1 for k in present_findings_keys if k in impression_keys)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Cobertura agregada, sem texto real de sentenca.",
        "distinct_finding_keys_findings_section": len(findings_keys),
        "distinct_finding_keys_impression_section": len(impression_keys),
        "present_finding_keys_with_own_impression_phrase": with_impression_phrase,
        "present_finding_keys_total": len(present_findings_keys),
        "pct_present_findings_with_dedicated_impression_phrase": (
            round(100 * with_impression_phrase / len(present_findings_keys), 1)
            if present_findings_keys else None
        ),
        "caveat": (
            "Quando nao ha frase de impressao dedicada para uma combinacao, "
            "o compilador reaproveita a frase de achados (ainda real, nunca "
            "inventada) — ver ResolvedFinding.exact_match=False nesses casos."
        ),
    }


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} nao existe. Rode ingest_vertical.py e extract_concepts.py antes.")

    conn = sqlite3.connect(DB_PATH)
    bank = build_phrase_bank(conn)

    run_demo(conn, bank)

    qa = compute_coverage_qa(conn)
    QA_DIR.mkdir(parents=True, exist_ok=True)
    (QA_DIR / "QA_REPORT_FASE6.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print()
    print(f"QA: {QA_DIR / 'QA_REPORT_FASE6.json'}")
    conn.close()


if __name__ == "__main__":
    main()
