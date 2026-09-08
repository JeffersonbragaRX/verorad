from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.api.db import get_db
from backend.api.schemas import ReviewQueueItemOut, ReviewQueueResolveIn
from backend.clinical.review_queue import resolve_review_item, reopen_review_item

router = APIRouter(prefix="/api/review-queue", tags=["review-queue"])


def _row_to_out(row: sqlite3.Row) -> ReviewQueueItemOut:
    return ReviewQueueItemOut(
        id=row["id"], report_id=row["report_id"], sentence_id=row["sentence_id"],
        section_type=row["section_type"], doctor=row["doctor"], exam_type=row["exam_type"],
        original_text=row["original_text"],
        system_output=json.loads(row["system_output_json"]),
        rule_id=row["rule_id"], reason=row["reason"], risk_level=row["risk_level"],
        status=row["status"], reviewer_note=row["reviewer_note"],
        created_at=row["created_at"], resolved_at=row["resolved_at"],
    )


@router.get("", response_model=list[ReviewQueueItemOut])
def list_review_queue(
    status: str | None = None,
    risk_level: str | None = None,
    reason: str | None = None,
    db: sqlite3.Connection = Depends(get_db),
):
    clauses = []
    params: list = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if risk_level:
        clauses.append("risk_level = ?")
        params.append(risk_level)
    if reason:
        clauses.append("reason = ?")
        params.append(reason)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    # risco alto primeiro, depois pendentes antes de resolvidos, mais recentes primeiro
    rows = db.execute(
        f"""SELECT * FROM clinical_review_queue {where}
            ORDER BY CASE risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                     CASE status WHEN 'pending' THEN 0 ELSE 1 END,
                     id DESC""",
        params,
    ).fetchall()
    return [_row_to_out(r) for r in rows]


@router.post("/{item_id}/resolve", response_model=ReviewQueueItemOut)
def resolve_item(item_id: int, body: ReviewQueueResolveIn, db: sqlite3.Connection = Depends(get_db)):
    if not resolve_review_item(db.cursor(), item_id, body.reviewer_note):
        raise HTTPException(status_code=404, detail="Item da fila não encontrado")
    db.commit()
    row = db.execute("SELECT * FROM clinical_review_queue WHERE id = ?", (item_id,)).fetchone()
    return _row_to_out(row)


@router.post("/{item_id}/reopen", response_model=ReviewQueueItemOut)
def reopen_item(item_id: int, db: sqlite3.Connection = Depends(get_db)):
    if not reopen_review_item(db.cursor(), item_id):
        raise HTTPException(status_code=404, detail="Item da fila não encontrado")
    db.commit()
    row = db.execute("SELECT * FROM clinical_review_queue WHERE id = ?", (item_id,)).fetchone()
    return _row_to_out(row)
