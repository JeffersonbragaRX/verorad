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
    unmatched_header INTEGER NOT NULL DEFAULT 0,
    -- rotulo adicional sem trocar o tipo: exam_title_*, implicit_lead_in,
    -- implicit_no_header, subsection:<rotulo>, unknown_subsection:<rotulo>
    section_subtype TEXT
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


# Tabela de julgamento humano (fila de revisao clinica). Ao contrario de
# `clinical_concepts`, esta tabela NAO e recriada do zero a cada
# execucao de extract_concepts.py — faria uma revisao/anotacao humana
# ja feita (status='resolved', reviewer_note) desaparecer a cada
# reprocessamento. Usa chave natural (sentence_id, reason) com UPSERT:
# conteudo extraido e atualizado, mas status/nota de revisao de um item
# ja existente sao preservados (ver ensure_review_queue_schema /
# sync_review_queue em extract_concepts.py). Prevista desde a ADR 0004.
REVIEW_QUEUE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS clinical_review_queue (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    sentence_id INTEGER NOT NULL REFERENCES sentences(id),
    section_type TEXT NOT NULL,
    doctor TEXT NOT NULL,
    exam_type TEXT NOT NULL,
    original_text TEXT NOT NULL,
    system_output_json TEXT NOT NULL,
    rule_id TEXT,
    reason TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer_note TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    UNIQUE(sentence_id, reason)
);

CREATE INDEX IF NOT EXISTS idx_review_queue_status ON clinical_review_queue(status);
CREATE INDEX IF NOT EXISTS idx_review_queue_risk ON clinical_review_queue(risk_level);
CREATE INDEX IF NOT EXISTS idx_review_queue_report ON clinical_review_queue(report_id);
"""


# ---- Camada universal (V2) -----------------------------------------
#
# Tabelas da Fase 4A/4B globais. Convivem com `clinical_concepts`
# (extrator do vertical de joelho, que continua alimentando o compilador
# e a interface da Fase 6 ate ela ser reconstruida sobre esta camada).
# Nao sao a mesma coisa e nao devem ser unidas por conveniencia: a
# tabela legada tem vocabulario hand-coded de joelho; esta e' derivada
# do lexico minerado e cobre os 210 tipos de exame.
UNIVERSAL_SCHEMA_SQL = """
DROP TABLE IF EXISTS clinical_lexicon;
DROP TABLE IF EXISTS clinical_concepts_universal;

CREATE TABLE clinical_lexicon (
    id INTEGER PRIMARY KEY,
    term TEXT NOT NULL UNIQUE,
    term_type TEXT NOT NULL,        -- anatomy|finding|attribute|descriptor|modifier|...
    method TEXT NOT NULL,           -- corpus_positional|morphological|model_knowledge
    confidence REAL NOT NULL,
    frequency INTEGER NOT NULL,
    n_exam_types INTEGER NOT NULL,
    top_exam_type TEXT NOT NULL,
    concentration REAL NOT NULL,
    p_after_preposition REAL NOT NULL,
    p_clause_initial REAL NOT NULL,
    p_after_finding_trigger REAL NOT NULL,
    domains TEXT NOT NULL,
    validation_status TEXT NOT NULL DEFAULT 'extraction_candidate',
    lexicon_version TEXT NOT NULL
);

CREATE INDEX idx_lexicon_type ON clinical_lexicon(term_type);
CREATE INDEX idx_lexicon_freq ON clinical_lexicon(frequency);

CREATE TABLE clinical_concepts_universal (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    section_id INTEGER NOT NULL REFERENCES report_sections(id),
    sentence_id INTEGER NOT NULL REFERENCES sentences(id),
    modality TEXT NOT NULL,
    domain TEXT NOT NULL,
    exam_type TEXT NOT NULL,
    doctor TEXT NOT NULL,
    section_type TEXT NOT NULL,
    structure TEXT,
    finding TEXT,
    status TEXT NOT NULL,
    certainty TEXT NOT NULL,
    severity TEXT,
    morphology TEXT,
    distribution TEXT,
    grade TEXT,
    laterality TEXT,
    laterality_source TEXT,
    measurements TEXT,
    measurement_unit TEXT,
    temporal_status TEXT,
    comparison_status TEXT,
    etiologic_qualifier TEXT,
    postoperative_context TEXT,
    modifiers TEXT,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    source_span TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    lexicon_version TEXT NOT NULL,
    layer_version TEXT NOT NULL,
    confidence REAL NOT NULL,
    validation_status TEXT NOT NULL
);

CREATE INDEX idx_cu_report ON clinical_concepts_universal(report_id);
CREATE INDEX idx_cu_exam ON clinical_concepts_universal(exam_type);
CREATE INDEX idx_cu_structure ON clinical_concepts_universal(structure);
CREATE INDEX idx_cu_finding ON clinical_concepts_universal(finding);
CREATE INDEX idx_cu_status ON clinical_concepts_universal(status);
CREATE INDEX idx_cu_sentence ON clinical_concepts_universal(sentence_id);
"""


def rebuild_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def rebuild_universal_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(UNIVERSAL_SCHEMA_SQL)
    conn.commit()


def rebuild_concepts_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(CONCEPTS_SCHEMA_SQL)
    conn.commit()


def ensure_review_queue_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(REVIEW_QUEUE_SCHEMA_SQL)
    conn.commit()
