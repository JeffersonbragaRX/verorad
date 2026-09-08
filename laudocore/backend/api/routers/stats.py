from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from backend.api.db import get_db
from backend.api.schemas import StatsOut

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats", response_model=StatsOut)
def get_stats(db: sqlite3.Connection = Depends(get_db)):
    reports_total = db.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    sentences_total = db.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    concepts_total = db.execute("SELECT COUNT(*) FROM clinical_concepts").fetchone()[0]
    pending = db.execute(
        "SELECT COUNT(*) FROM clinical_review_queue WHERE status = 'pending'"
    ).fetchone()[0]
    resolved = db.execute(
        "SELECT COUNT(*) FROM clinical_review_queue WHERE status = 'resolved'"
    ).fetchone()[0]
    by_risk = dict(db.execute(
        "SELECT risk_level, COUNT(*) FROM clinical_review_queue WHERE status='pending' "
        "GROUP BY risk_level"
    ).fetchall())
    doctors = [r[0] for r in db.execute("SELECT DISTINCT doctor FROM reports ORDER BY doctor")]
    exam_types = [r[0] for r in db.execute("SELECT DISTINCT exam_type FROM reports ORDER BY exam_type")]

    return StatsOut(
        reports_total=reports_total, sentences_total=sentences_total,
        concepts_total=concepts_total, review_queue_pending=pending,
        review_queue_resolved=resolved, review_queue_by_risk=by_risk,
        doctors=doctors, exam_types=exam_types,
    )
