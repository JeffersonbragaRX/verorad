"""Modelos Pydantic (request/response) da API. Nenhum dado mockado —
toda instancia vem de uma consulta real ao banco."""

from __future__ import annotations

from pydantic import BaseModel


class ReportSummary(BaseModel):
    id: int
    record_id: int
    doctor: str
    exam_type: str
    laterality: str | None
    age_at_exam: int | None
    sex: str | None
    exam_datetime: str | None


class SentenceOut(BaseModel):
    id: int
    text_raw: str
    section_type: str
    concepts: list["ConceptOut"]


class ConceptOut(BaseModel):
    id: int
    structure: str
    structure_label: str
    finding: str
    finding_label: str
    status: str
    status_label: str
    severity: str | None
    severity_label: str
    location: str | None
    location_label: str
    measurement_cm: float | None
    certainty: str
    rule_id: str


class SectionOut(BaseModel):
    id: int
    section_type: str
    text_raw: str
    header_line: str | None
    unmatched_header: bool
    sentences: list[SentenceOut]


class ReportDetail(BaseModel):
    id: int
    record_id: int
    doctor: str
    exam_type: str
    laterality: str | None
    age_at_exam: int | None
    sex: str | None
    exam_datetime: str | None
    report_text_raw: str
    sections: list[SectionOut]


class PhraseLibraryEntry(BaseModel):
    structure: str
    structure_label: str
    finding: str
    finding_label: str
    status: str
    status_label: str
    severity: str | None
    severity_label: str
    location: str | None
    location_label: str
    section_type: str
    example_text: str
    frequency: int
    doctors: list[str]


class TaxonomyOption(BaseModel):
    structure: str
    structure_label: str
    finding: str
    finding_label: str
    status: str
    status_label: str
    severity: str | None
    severity_label: str
    location: str | None
    location_label: str
    frequency: int


class FindingRequestIn(BaseModel):
    structure: str
    finding: str
    status: str = "present"
    severity: str | None = None
    location: str | None = None


class CompileRequestIn(BaseModel):
    findings: list[FindingRequestIn]
    doctor: str | None = None
    indication_text: str | None = None


class ResolvedFindingOut(BaseModel):
    structure: str
    structure_label: str
    finding: str
    finding_label: str
    status: str
    severity: str | None
    location: str | None
    text: str
    source_doctor: str
    exact_match: bool


class CompileResponseOut(BaseModel):
    technique_text: str | None
    findings_lines: list[ResolvedFindingOut]
    impression_lines: list[ResolvedFindingOut]
    unresolved: list[FindingRequestIn]
    warnings: list[str]
    rendered_text: str


class ReviewQueueItemOut(BaseModel):
    id: int
    report_id: int
    sentence_id: int
    section_type: str
    doctor: str
    exam_type: str
    original_text: str
    system_output: list[dict]
    rule_id: str | None
    reason: str
    risk_level: str
    status: str
    reviewer_note: str | None
    created_at: str
    resolved_at: str | None


class ReviewQueueResolveIn(BaseModel):
    reviewer_note: str | None = None


class StatsOut(BaseModel):
    reports_total: int
    sentences_total: int
    concepts_total: int
    review_queue_pending: int
    review_queue_resolved: int
    review_queue_by_risk: dict[str, int]
    doctors: list[str]
    exam_types: list[str]
