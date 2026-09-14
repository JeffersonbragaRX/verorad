"""Endpoints da camada de ANALISE (V2) — leem clinical_concepts_universal
e clinical_lexicon, nunca a tabela legada do vertical de joelho.

Regra desta camada (secao 19 do PROMPT MESTRE V2): a interface nao pode
dar aparencia de validacao clinica a conteudo nao revisado. Todo
endpoint devolve, junto do numero, o status de validacao e a
proveniencia — o frontend mostra os dois lado a lado.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.db import get_db

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "data" / "derived" / "artifacts"


def _read_csv(name: str) -> list[dict]:
    path = ARTIFACTS / name
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=(f"{name} ainda nao foi gerado. Rode "
                     "scripts/mine_clinical_layer.py e "
                     "scripts/analyze_clinical_corpus.py."),
        )
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _read_json(name: str):
    path = ARTIFACTS / name
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"{name} ainda nao foi gerado.")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/overview")
def overview(db: sqlite3.Connection = Depends(get_db)):
    """Numeros do corpus inteiro, para a tela de cobertura."""
    def one(sql: str):
        return db.execute(sql).fetchone()[0]

    return {
        "reports": one("SELECT COUNT(*) FROM reports"),
        "patients": one("SELECT COUNT(DISTINCT patient_id) FROM reports"),
        "sentences": one("SELECT COUNT(*) FROM sentences"),
        "exam_types": one("SELECT COUNT(DISTINCT exam_type) FROM reports"),
        "doctors": one("SELECT COUNT(DISTINCT doctor) FROM reports"),
        "domains": one("SELECT COUNT(DISTINCT domain) FROM reports"),
        "concepts": one("SELECT COUNT(*) FROM clinical_concepts_universal"),
        "lexicon_terms": one("SELECT COUNT(*) FROM clinical_lexicon"),
        "by_modality": dict(db.execute(
            "SELECT modality, COUNT(*) FROM reports GROUP BY modality ORDER BY 2 DESC").fetchall()),
        "by_domain": dict(db.execute(
            "SELECT domain, COUNT(*) FROM reports GROUP BY domain ORDER BY 2 DESC").fetchall()),
        "by_status": dict(db.execute(
            "SELECT status, COUNT(*) FROM clinical_concepts_universal "
            "GROUP BY status ORDER BY 2 DESC").fetchall()),
        "validation_note": (
            "Nenhum conceito desta camada foi validado clinicamente. "
            "Todos estao em extraction_candidate."),
    }


@router.get("/coverage")
def coverage(
    status: str | None = None,
    modality: str | None = None,
    search: str | None = None,
    limit: int = Query(300, le=1000),
):
    rows = _read_csv("CLINICAL_COVERAGE_MATRIX.csv")
    if status:
        rows = [r for r in rows if r["validation_status"] == status]
    if modality:
        rows = [r for r in rows if r["modality"] == modality]
    if search:
        needle = search.lower()
        rows = [r for r in rows if needle in r["exam_type"].lower()
                or needle in (r["anatomy"] or "").lower()]
    rows.sort(key=lambda r: -int(r["reports"]))
    return rows[:limit]


@router.get("/exam-profile/{exam_type}")
def exam_profile(exam_type: str):
    profiles = _read_json("EXAM_TYPE_CLINICAL_PROFILES.json")
    if exam_type not in profiles:
        raise HTTPException(status_code=404, detail="exam_type sem perfil gerado")
    return profiles[exam_type]


@router.get("/associations")
def associations(
    exam_type: str | None = None,
    min_effect: float = 0.0,
    max_q: float = 0.05,
    exclude_artifacts: bool = True,
    min_doctors: int = 1,
    limit: int = Query(200, le=2000),
):
    rows = _read_csv("ASSOCIATION_STATISTICS.csv")
    out = []
    for r in rows:
        if exam_type and r["exam_type"] != exam_type:
            continue
        if exclude_artifacts and r["mutually_locked_artifact"] == "True":
            continue
        if float(r["q_value"]) > max_q:
            continue
        if abs(float(r["absolute_difference"])) < min_effect:
            continue
        if int(r["n_doctors"]) < min_doctors:
            continue
        out.append(r)
    out.sort(key=lambda r: -abs(float(r["absolute_difference"])))
    return out[:limit]


@router.get("/unmodeled-tail")
def unmodeled_tail(priority: str | None = None, limit: int = Query(200, le=2000)):
    rows = _read_csv("UNMODELED_CLINICAL_TAIL.csv")
    if priority:
        rows = [r for r in rows if r["priority"] == priority]
    return rows[:limit]


@router.get("/normality")
def normality(exam_type: str | None = None, limit: int = Query(200, le=2000)):
    rows = _read_csv("NORMALITY_CANDIDATES.csv")
    if exam_type:
        rows = [r for r in rows if r["exam_type"] == exam_type]
    return rows[:limit]


@router.get("/physicians")
def physicians():
    return {
        "comparison": _read_csv("PHYSICIAN_STYLE_COMPARISON.csv"),
        "profiles": _read_json("PHYSICIAN_STYLE_PROFILES.json"),
    }


@router.get("/body-vs-impression")
def body_vs_impression(limit: int = Query(200, le=2000)):
    rows = _read_csv("CONCLUSION_MAPPINGS.csv")
    rows.sort(key=lambda r: -int(r["n_reports_with_finding_in_body"]))
    return rows[:limit]


@router.get("/lexicon")
def lexicon(
    term_type: str | None = None,
    method: str | None = None,
    search: str | None = None,
    limit: int = Query(200, le=2000),
    db: sqlite3.Connection = Depends(get_db),
):
    sql = ["SELECT term, term_type, method, confidence, frequency, n_exam_types,",
           "top_exam_type, concentration, p_after_preposition,",
           "p_after_finding_trigger, domains, validation_status",
           "FROM clinical_lexicon WHERE 1=1"]
    params: list = []
    if term_type:
        sql.append("AND term_type = ?")
        params.append(term_type)
    if method:
        sql.append("AND method = ?")
        params.append(method)
    if search:
        sql.append("AND term LIKE ?")
        params.append(f"%{search.lower()}%")
    sql.append("ORDER BY frequency DESC LIMIT ?")
    params.append(limit)
    cols = ["term", "term_type", "method", "confidence", "frequency", "n_exam_types",
            "top_exam_type", "concentration", "p_after_preposition",
            "p_after_finding_trigger", "domains", "validation_status"]
    return [dict(zip(cols, row)) for row in db.execute(" ".join(sql), params).fetchall()]


@router.get("/concepts")
def concepts(
    exam_type: str | None = None,
    finding: str | None = None,
    status: str | None = None,
    laterality_conflict: bool = False,
    limit: int = Query(100, le=500),
    db: sqlite3.Connection = Depends(get_db),
):
    """Navegador de conceitos COM a sentenca de origem — a proveniencia
    e' parte do dado, nao um extra."""
    sql = ["""SELECT cu.id, cu.exam_type, cu.doctor, cu.section_type, cu.structure,
                     cu.finding, cu.status, cu.certainty, cu.severity, cu.morphology,
                     cu.distribution, cu.grade, cu.laterality, cu.laterality_source,
                     cu.measurements, cu.temporal_status, cu.comparison_status,
                     cu.etiologic_qualifier, cu.postoperative_context,
                     cu.source_span, cu.rule_id, cu.confidence, cu.validation_status,
                     s.text_raw
              FROM clinical_concepts_universal cu
              JOIN sentences s ON cu.sentence_id = s.id
              WHERE 1=1"""]
    params: list = []
    if exam_type:
        sql.append("AND cu.exam_type = ?")
        params.append(exam_type)
    if finding:
        sql.append("AND cu.finding LIKE ?")
        params.append(f"%{finding.lower()}%")
    if status:
        sql.append("AND cu.status = ?")
        params.append(status)
    if laterality_conflict:
        sql.append("AND cu.laterality_source = 'conflict'")
    sql.append("LIMIT ?")
    params.append(limit)
    cols = ["id", "exam_type", "doctor", "section_type", "structure", "finding",
            "status", "certainty", "severity", "morphology", "distribution", "grade",
            "laterality", "laterality_source", "measurements", "temporal_status",
            "comparison_status", "etiologic_qualifier", "postoperative_context",
            "source_span", "rule_id", "confidence", "validation_status", "sentence_text"]
    return [dict(zip(cols, row)) for row in db.execute(" ".join(sql), params).fetchall()]


@router.get("/eval")
def eval_report():
    return _read_json("CLINICAL_EVAL_REPORT.json")
