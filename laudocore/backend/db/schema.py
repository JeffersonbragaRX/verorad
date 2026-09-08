"""Schema relacional local (SQLite) para a Fase 1.

Ver docs/decisions/0004-sqlite-para-fase1.md: SQLite e usado como
persistencia local nesta fase (escopo restrito a um vertical, ~900
registros); a migracao para PostgreSQL (stack alvo da especificacao)
e mecanica porque o modelo relacional e o mesmo.
"""

from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
DROP TABLE IF EXISTS sentences;
DROP TABLE IF EXISTS report_sections;
DROP TABLE IF EXISTS reports;

CREATE TABLE reports (
    id INTEGER PRIMARY KEY,
    record_id INTEGER UNIQUE NOT NULL,
    patient_id TEXT NOT NULL,
    age_at_exam INTEGER,
    sex TEXT,
    exam_datetime TEXT,
    modality TEXT NOT NULL,
    domain TEXT,
    anatomy TEXT,
    laterality TEXT,
    exam_type TEXT NOT NULL,
    study_description_raw TEXT,
    doctor TEXT NOT NULL,
    report_text_raw TEXT NOT NULL,
    report_text_clean TEXT NOT NULL,
    report_text_normalized TEXT NOT NULL,
    exact_hash TEXT NOT NULL,
    normalized_hash TEXT NOT NULL,
    source TEXT NOT NULL,
    import_batch TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE report_sections (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    section_type TEXT NOT NULL,
    section_order INTEGER NOT NULL,
    text_raw TEXT NOT NULL,
    text_clean TEXT NOT NULL,
    header_line TEXT,
    unmatched_header INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE sentences (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    section_id INTEGER NOT NULL REFERENCES report_sections(id),
    sentence_order INTEGER NOT NULL,
    text_raw TEXT NOT NULL,
    text_normalized TEXT NOT NULL,
    doctor TEXT NOT NULL,
    exam_type TEXT NOT NULL,
    exact_hash TEXT NOT NULL,
    normalized_hash TEXT NOT NULL
);

CREATE INDEX idx_reports_exam_type ON reports(exam_type);
CREATE INDEX idx_reports_doctor ON reports(doctor);
CREATE INDEX idx_sections_report ON report_sections(report_id);
CREATE INDEX idx_sections_type ON report_sections(section_type);
CREATE INDEX idx_sentences_report ON sentences(report_id);
CREATE INDEX idx_sentences_exact_hash ON sentences(exact_hash);
"""

# Tabela separada (schema/migração proprios) porque e populada por um
# script diferente (extract_concepts.py, Fase 4) que roda DEPOIS da
# ingestao e nao deve exigir reingestao completa para ser reexecutado.
CONCEPTS_SCHEMA_SQL = """
DROP TABLE IF EXISTS clinical_concepts;

CREATE TABLE clinical_concepts (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    sentence_id INTEGER NOT NULL REFERENCES sentences(id),
    section_type TEXT NOT NULL,
    organ TEXT NOT NULL,
    structure TEXT NOT NULL,
    finding TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT,
    location TEXT,
    measurement_cm REAL,
    certainty TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    doctor TEXT NOT NULL,
    exam_type TEXT NOT NULL
);

CREATE INDEX idx_concepts_report ON clinical_concepts(report_id);
CREATE INDEX idx_concepts_structure ON clinical_concepts(structure);
CREATE INDEX idx_concepts_finding ON clinical_concepts(finding);
"""


def rebuild_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def rebuild_concepts_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(CONCEPTS_SCHEMA_SQL)
    conn.commit()
