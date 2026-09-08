from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from backend.api.db import get_db
from backend.api.schemas import TaxonomyOption, PhraseLibraryEntry
from backend.clinical.labels import (
    structure_label, finding_label, status_label, location_label, severity_label,
)
from backend.compiler.phrase_bank import build_phrase_bank

router = APIRouter(prefix="/api", tags=["concepts"])


@router.get("/taxonomy", response_model=list[TaxonomyOption])
def get_taxonomy(db: sqlite3.Connection = Depends(get_db)):
    """Todas as combinacoes (estrutura, achado, status, gravidade,
    localizacao) realmente observadas no corpus — usado para montar os
    seletores de 'inserir achado' na UI. Nunca inclui uma combinacao
    que nao tenha pelo menos uma frase real por tras."""
    rows = db.execute(
        """
        SELECT structure, finding, status, severity, location, COUNT(*) as frequency
        FROM clinical_concepts
        GROUP BY structure, finding, status, severity, location
        ORDER BY frequency DESC
        """
    ).fetchall()
    return [
        TaxonomyOption(
            structure=r["structure"], structure_label=structure_label(r["structure"]),
            finding=r["finding"], finding_label=finding_label(r["finding"]),
            status=r["status"], status_label=status_label(r["status"]),
            severity=r["severity"], severity_label=severity_label(r["severity"]),
            location=r["location"], location_label=location_label(r["location"]),
            frequency=r["frequency"],
        )
        for r in rows
    ]


@router.get("/phrases", response_model=list[PhraseLibraryEntry])
def search_phrases(
    structure: str | None = None,
    finding: str | None = None,
    status: str | None = None,
    search: str | None = None,
    db: sqlite3.Connection = Depends(get_db),
):
    """Biblioteca de frases reais por achado — 'localizar e filtrar
    achados' na UI. Cada entrada mostra a frase mais representativa e
    de quais medicos ela vem (nunca prosa gerada, sempre uma frase que
    ja existe em algum laudo real)."""
    bank = build_phrase_bank(db)
    entries = bank.entries()

    if structure:
        entries = [e for e in entries if e["structure"] == structure]
    if finding:
        entries = [e for e in entries if e["finding"] == finding]
    if status:
        entries = [e for e in entries if e["status"] == status]
    if search:
        needle = search.casefold()
        entries = [e for e in entries if needle in e["example_text"].casefold()]

    entries.sort(key=lambda e: -e["frequency"])

    return [
        PhraseLibraryEntry(
            structure=e["structure"], structure_label=structure_label(e["structure"]),
            finding=e["finding"], finding_label=finding_label(e["finding"]),
            status=e["status"], status_label=status_label(e["status"]),
            severity=e["severity"], severity_label=severity_label(e["severity"]),
            location=e["location"], location_label=location_label(e["location"]),
            section_type=e["section_type"], example_text=e["example_text"],
            frequency=e["frequency"], doctors=e["doctors"],
        )
        for e in entries
    ]
