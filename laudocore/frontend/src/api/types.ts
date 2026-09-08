// Espelha backend/api/schemas.py — mantenha em sincronia manualmente
// (projeto pequeno o suficiente para nao justificar geracao automatica
// de tipos a partir do OpenAPI ainda).

export interface ReportSummary {
  id: number
  record_id: number
  doctor: string
  exam_type: string
  laterality: string | null
  age_at_exam: number | null
  sex: string | null
  exam_datetime: string | null
}

export interface ConceptOut {
  id: number
  structure: string
  structure_label: string
  finding: string
  finding_label: string
  status: string
  status_label: string
  severity: string | null
  severity_label: string
  location: string | null
  location_label: string
  measurement_cm: number | null
  certainty: string
  rule_id: string
}

export interface SentenceOut {
  id: number
  text_raw: string
  section_type: string
  concepts: ConceptOut[]
}

export interface SectionOut {
  id: number
  section_type: string
  text_raw: string
  header_line: string | null
  unmatched_header: boolean
  sentences: SentenceOut[]
}

export interface ReportDetail extends ReportSummary {
  report_text_raw: string
  sections: SectionOut[]
}

export interface TaxonomyOption {
  structure: string
  structure_label: string
  finding: string
  finding_label: string
  status: string
  status_label: string
  severity: string | null
  severity_label: string
  location: string | null
  location_label: string
  frequency: number
}

export interface PhraseLibraryEntry extends TaxonomyOption {
  section_type: string
  example_text: string
  doctors: string[]
}

export interface FindingRequestIn {
  structure: string
  finding: string
  status: string
  severity: string | null
  location: string | null
}

export interface ResolvedFindingOut {
  structure: string
  structure_label: string
  finding: string
  finding_label: string
  status: string
  severity: string | null
  location: string | null
  text: string
  source_doctor: string
  exact_match: boolean
}

export interface CompileResponse {
  technique_text: string | null
  findings_lines: ResolvedFindingOut[]
  impression_lines: ResolvedFindingOut[]
  unresolved: FindingRequestIn[]
  warnings: string[]
  rendered_text: string
}

export interface ReviewQueueItem {
  id: number
  report_id: number
  sentence_id: number
  section_type: string
  doctor: string
  exam_type: string
  original_text: string
  system_output: Record<string, unknown>[]
  rule_id: string | null
  reason: string
  risk_level: 'low' | 'medium' | 'high'
  status: 'pending' | 'resolved'
  reviewer_note: string | null
  created_at: string
  resolved_at: string | null
}

export interface Stats {
  reports_total: number
  sentences_total: number
  concepts_total: number
  review_queue_pending: number
  review_queue_resolved: number
  review_queue_by_risk: Record<string, number>
  doctors: string[]
  exam_types: string[]
}
