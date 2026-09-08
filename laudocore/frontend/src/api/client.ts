import type {
  ReportSummary, ReportDetail, TaxonomyOption, PhraseLibraryEntry,
  FindingRequestIn, CompileResponse, ReviewQueueItem, Stats,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    throw new ApiError(0, 'Não foi possível conectar ao servidor. Verifique se o backend está rodando.')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // corpo nao era JSON, mantem statusText
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const usable = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  if (usable.length === 0) return ''
  return '?' + new URLSearchParams(usable.map(([k, v]) => [k, String(v)])).toString()
}

export const api = {
  stats: () => request<Stats>('/api/stats'),

  listReports: (params: {
    doctor?: string; exam_type?: string; laterality?: string; search?: string
    limit?: number; offset?: number
  } = {}) => request<ReportSummary[]>(`/api/reports${qs(params)}`),

  getReport: (id: number) => request<ReportDetail>(`/api/reports/${id}`),

  taxonomy: () => request<TaxonomyOption[]>('/api/taxonomy'),

  searchPhrases: (params: {
    structure?: string; finding?: string; status?: string; search?: string
  } = {}) => request<PhraseLibraryEntry[]>(`/api/phrases${qs(params)}`),

  compile: (body: { findings: FindingRequestIn[]; doctor?: string | null; indication_text?: string | null }) =>
    request<CompileResponse>('/api/compile', { method: 'POST', body: JSON.stringify(body) }),

  listReviewQueue: (params: { status?: string; risk_level?: string; reason?: string } = {}) =>
    request<ReviewQueueItem[]>(`/api/review-queue${qs(params)}`),

  resolveReviewItem: (id: number, reviewer_note?: string) =>
    request<ReviewQueueItem>(`/api/review-queue/${id}/resolve`, {
      method: 'POST', body: JSON.stringify({ reviewer_note: reviewer_note ?? null }),
    }),

  reopenReviewItem: (id: number) =>
    request<ReviewQueueItem>(`/api/review-queue/${id}/reopen`, { method: 'POST' }),
}
