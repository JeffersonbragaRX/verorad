from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from backend.api.db import get_db
from backend.api.schemas import (
    CompileRequestIn, CompileResponseOut, ResolvedFindingOut, FindingRequestIn,
    TechniqueSuggestionOut,
)
from backend.clinical.labels import structure_label, finding_label
from backend.compiler.phrase_bank import build_phrase_bank
from backend.compiler.report_compiler import FindingRequest, compile_report, suggest_technique_candidates

router = APIRouter(prefix="/api", tags=["compile"])


def _resolved_out(rf) -> ResolvedFindingOut:
    return ResolvedFindingOut(
        structure=rf.request.structure, structure_label=structure_label(rf.request.structure),
        finding=rf.request.finding, finding_label=finding_label(rf.request.finding),
        status=rf.request.status, severity=rf.request.severity, location=rf.request.location,
        text=rf.text, source_doctor=rf.source_doctor, exact_match=rf.exact_match,
    )


@router.post("/compile", response_model=CompileResponseOut)
def compile_endpoint(body: CompileRequestIn, db: sqlite3.Connection = Depends(get_db)):
    findings = [
        FindingRequest(f.structure, f.finding, f.status, f.severity, f.location)
        for f in body.findings
    ]
    bank = build_phrase_bank(db)
    result = compile_report(
        db, findings, doctor=body.doctor, laterality=body.laterality,
        technique_text=body.technique_text, phrase_bank=bank,
    )

    return CompileResponseOut(
        technique_text=result.technique_text,
        findings_lines=[_resolved_out(rf) for rf in result.findings_lines],
        impression_lines=[_resolved_out(rf) for rf in result.impression_lines],
        unresolved=[
            FindingRequestIn(structure=f.structure, finding=f.finding, status=f.status,
                              severity=f.severity, location=f.location)
            for f in result.unresolved
        ],
        warnings=result.warnings,
        blocking=result.blocking,
        rendered_text=result.render(indication_text=body.indication_text),
    )


@router.get("/technique-suggestions", response_model=list[TechniqueSuggestionOut])
def technique_suggestions_endpoint(
    doctor: str | None = None, db: sqlite3.Connection = Depends(get_db),
):
    """Sugestoes de tecnica reais de OUTROS exames do corpus — nunca
    aplicadas automaticamente (ver ADR 0010). O medico escolhe uma (ou
    escreve a propria) e envia como 'technique_text' em /api/compile."""
    return [
        TechniqueSuggestionOut(**c) for c in suggest_technique_candidates(db, doctor=doctor)
    ]
