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
  blocking: boolean
  rendered_text: string
}

export interface TechniqueSuggestion {
  text: string
  doctor: string
  frequency: number
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

// ---- Camada de ANALISE (V2, corpus inteiro) -------------------------
// Espelha backend/api/routers/analysis.py. Os CSVs sao servidos como
// linhas de string (vem de csv.DictReader), entao os campos numericos
// chegam como string e sao convertidos no ponto de uso.

export interface AnalysisOverview {
  reports: number
  patients: number
  sentences: number
  exam_types: number
  doctors: number
  domains: number
  concepts: number
  lexicon_terms: number
  by_modality: Record<string, number>
  by_domain: Record<string, number>
  by_status: Record<string, number>
  validation_note: string
}

export interface CoverageRow {
  exam_type: string
  modality: string
  domain: string
  anatomy: string
  reports: string
  patients: string
  doctors: string
  clinical_sentences: string
  concept_coverage_pct: string
  concepts: string
  structure_binding_pct: string
  laterality_conflicts: string
  validation_status: string
  limitations: string
  next_pending_step: string
}

export interface AssociationRow {
  exam_type: string
  antecedent_concept: string
  consequent_concept: string
  support_n: string
  support_n_without_dedup: string
  eligible_denominator: string
  n_patients: string
  n_doctors: string
  doctors: string
  p_b_given_a: string
  p_b_without_a: string
  absolute_difference: string
  prevalence_ratio: string
  pr_ci_low: string
  pr_ci_high: string
  q_value: string
  mutually_locked_artifact: string
  single_author_evidence: string
  interpretation_allowed: string
}

export interface UniversalConcept {
  id: number
  exam_type: string
  doctor: string
  section_type: string
  structure: string | null
  finding: string | null
  status: string
  certainty: string
  severity: string | null
  morphology: string | null
  distribution: string | null
  grade: string | null
  laterality: string | null
  laterality_source: string | null
  measurements: string | null
  temporal_status: string | null
  comparison_status: string | null
  etiologic_qualifier: string | null
  postoperative_context: string | null
  source_span: string
  rule_id: string
  confidence: number
  validation_status: string
  sentence_text: string
}

export interface TailRow {
  term: string
  frequency: string
  n_exam_types: string
  top_exam_type: string
  p_after_preposition: string
  priority: string
  reason_not_modeled: string
}

export interface PhysicianComparisonRow {
  doctor: string
  reports: string
  exam_types_covered: string
  concepts_per_report: string
  pct_with_impression: string
  pct_negated: string
  pct_explicit_normality: string
  pct_hedged: string
}

export interface PhysicianProfile {
  reports: number
  exam_types_covered: number
  top_findings: [string, number][]
  top_structures_declared_normal: [string, number][]
}

export interface PhysiciansPayload {
  comparison: PhysicianComparisonRow[]
  profiles: Record<string, PhysicianProfile>
}
