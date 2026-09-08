from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.db import get_db
from backend.api.schemas import (
    ReportSummary, ReportDetail, SectionOut, SentenceOut, ConceptOut,
)
from backend.clinical.labels import (
    structure_label, finding_label, status_label, location_label, severity_label,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _concept_row_to_out(row: sqlite3.Row) -> ConceptOut:
    return ConceptOut(
        id=row["id"], structure=row["structure"], structure_label=structure_label(row["structure"]),
        finding=row["finding"], finding_label=finding_label(row["finding"]),
        status=row["status"], status_label=status_label(row["status"]),
        severity=row["severity"], severity_label=severity_label(row["severity"]),
        location=row["location"], location_label=location_label(row["location"]),
        measurement_cm=row["measurement_cm"], certainty=row["certainty"], rule_id=row["rule_id"],
    )


@router.get("", response_model=list[ReportSummary])
def list_reports(
    doctor: str | None = None,
    exam_type: str | None = None,
    laterality: str | None = None,
    search: str | None = Query(None, description="busca em texto do laudo (raw)"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: sqlite3.Connection = Depends(get_db),
):
    clauses = []
    params: list = []
    if doctor:
        clauses.append("doctor = ?")
        params.append(doctor)
    if exam_type:
        clauses.append("exam_type = ?")
        params.append(exam_type)
    if laterality:
        clauses.append("laterality = ?")
        params.append(laterality)
    if search:
        clauses.append("report_text_raw LIKE ?")
        params.append(f"%{search}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.execute(
        f"""SELECT id, record_id, doctor, exam_type, laterality, age_at_exam, sex, exam_datetime
            FROM reports {where} ORDER BY id LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    ).fetchall()
    return [ReportSummary(**dict(r)) for r in rows]


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(report_id: int, db: sqlite3.Connection = Depends(get_db)):
    report_row = db.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if report_row is None:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")

    section_rows = db.execute(
        "SELECT * FROM report_sections WHERE report_id = ? ORDER BY section_order",
        (report_id,),
    ).fetchall()

    sections = []
    for srow in section_rows:
        sentence_rows = db.execute(
            "SELECT * FROM sentences WHERE section_id = ? ORDER BY sentence_order",
            (srow["id"],),
        ).fetchall()
        sentences = []
        for sent in sentence_rows:
            concept_rows = db.execute(
                "SELECT * FROM clinical_concepts WHERE sentence_id = ?", (sent["id"],)
            ).fetchall()
            sentences.append(SentenceOut(
                id=sent["id"], text_raw=sent["text_raw"], section_type=srow["section_type"],
                concepts=[_concept_row_to_out(c) for c in concept_rows],
            ))
        sections.append(SectionOut(
            id=srow["id"], section_type=srow["section_type"], text_raw=srow["text_raw"],
            header_line=srow["header_line"], unmatched_header=bool(srow["unmatched_header"]),
            sentences=sentences,
        ))

    return ReportDetail(
        id=report_row["id"], record_id=report_row["record_id"], doctor=report_row["doctor"],
        exam_type=report_row["exam_type"], laterality=report_row["laterality"],
        age_at_exam=report_row["age_at_exam"], sex=report_row["sex"],
        exam_datetime=report_row["exam_datetime"], report_text_raw=report_row["report_text_raw"],
        sections=sections,
    )
