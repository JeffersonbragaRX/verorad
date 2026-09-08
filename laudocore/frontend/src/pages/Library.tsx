import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { PageHeader } from '../components/PageHeader'
import { Badge, Card, EmptyState, ErrorBanner, Skeleton, Spinner } from '../components/ui'
import type { ReportSummary } from '../api/types'

export function Library() {
  const { id } = useParams()
  const navigate = useNavigate()
  const searchRef = useRef<HTMLInputElement>(null)

  const [doctor, setDoctor] = useState('')
  const [examType, setExamType] = useState('')
  const [laterality, setLaterality] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')

  const { data: stats } = useAsync(() => api.stats(), [])

  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), 300)
    return () => clearTimeout(t)
  }, [searchInput])

  const { data: reports, loading, error, reload } = useAsync(
    () => api.listReports({ doctor: doctor || undefined, exam_type: examType || undefined, laterality: laterality || undefined, search: search || undefined, limit: 100 }),
    [doctor, examType, laterality, search],
  )

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === '/' && document.activeElement !== searchRef.current) {
        e.preventDefault()
        searchRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Biblioteca de laudos"
        description="Busque um laudo real do vertical e veja o texto original ao lado da classificação extraída."
      />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex w-96 shrink-0 flex-col border-r border-[var(--color-border)] bg-white">
          <div className="space-y-2.5 border-b border-[var(--color-border)] p-4">
            <div className="relative">
              <input
                ref={searchRef}
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Buscar no texto do laudo…"
                className="w-full rounded-lg border border-[var(--color-border-strong)] px-3 py-2 pr-10 text-sm outline-none focus:border-[var(--color-accent)]"
              />
              <kbd className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-[var(--color-border)] px-1.5 py-0.5 text-[10px] text-[var(--color-ink-faint)]">
                /
              </kbd>
            </div>
            <div className="flex gap-2">
              <select
                value={doctor}
                onChange={(e) => setDoctor(e.target.value)}
                className="flex-1 rounded-lg border border-[var(--color-border-strong)] bg-white px-2 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
              >
                <option value="">Todos os médicos</option>
                {stats?.doctors.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
              <select
                value={laterality}
                onChange={(e) => setLaterality(e.target.value)}
                className="w-28 rounded-lg border border-[var(--color-border-strong)] bg-white px-2 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
              >
                <option value="">Lado</option>
                <option value="D">Direito</option>
                <option value="E">Esquerdo</option>
              </select>
            </div>
            <select
              value={examType}
              onChange={(e) => setExamType(e.target.value)}
              className="w-full rounded-lg border border-[var(--color-border-strong)] bg-white px-2 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
            >
              <option value="">Todos os tipos de exame</option>
              {stats?.exam_types.map((e) => (
                <option key={e} value={e}>{e}</option>
              ))}
            </select>
          </div>

          <div className="flex-1 overflow-y-auto">
            {error && <div className="p-4"><ErrorBanner message={error} onRetry={reload} /></div>}
            {loading && (
              <div className="space-y-2 p-4">
                {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-14" />)}
              </div>
            )}
            {reports && reports.length === 0 && (
              <div className="p-4">
                <EmptyState title="Nenhum laudo encontrado" hint="Ajuste os filtros ou o termo de busca." />
              </div>
            )}
            {reports?.map((r) => (
              <ReportRow key={r.id} report={r} active={String(r.id) === id} onClick={() => navigate(`/biblioteca/${r.id}`)} />
            ))}
          </div>
          {reports && (
            <div className="border-t border-[var(--color-border)] px-4 py-2 text-xs text-[var(--color-ink-faint)]">
              {reports.length} laudo(s) exibido(s) {reports.length === 100 && '(limite de 100 — refine a busca)'}
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto bg-[var(--color-bg-subtle)]">
          {id ? <ReportDetailPane id={Number(id)} /> : (
            <div className="p-8">
              <EmptyState title="Selecione um laudo" hint="Escolha um item na lista à esquerda para ver o texto original e a classificação extraída." />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ReportRow({ report, active, onClick }: { report: ReportSummary; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={
        'flex w-full flex-col gap-0.5 border-b border-[var(--color-border)] px-4 py-3 text-left transition-colors ' +
        (active ? 'bg-[var(--color-accent-subtle)]' : 'hover:bg-[var(--color-bg-subtle)]')
      }
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-[var(--color-ink)]">{report.doctor}</span>
        <span className="text-xs text-[var(--color-ink-faint)]">#{report.record_id}</span>
      </div>
      <div className="flex items-center gap-1.5 text-xs text-[var(--color-ink-muted)]">
        <span>{report.exam_type}</span>
        {report.laterality && <Badge>{report.laterality === 'D' ? 'Direito' : 'Esquerdo'}</Badge>}
        <span>· {report.sex ?? '—'}, {report.age_at_exam ?? '—'}a</span>
      </div>
    </button>
  )
}

function ReportDetailPane({ id }: { id: number }) {
  const { data: report, loading, error, reload } = useAsync(() => api.getReport(id), [id])

  if (loading) return <div className="p-8"><Spinner label="Carregando laudo…" /></div>
  if (error) return <div className="p-8"><ErrorBanner message={error} onRetry={reload} /></div>
  if (!report) return null

  const sectionLabels: Record<string, string> = {
    indication: 'Indicação clínica', technique: 'Técnica', comparison: 'Comparação',
    findings: 'Relatório', impression: 'Impressão diagnóstica', other: 'Outro',
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-8">
      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span className="font-semibold text-[var(--color-ink)]">{report.doctor}</span>
          <span className="text-[var(--color-ink-muted)]">{report.exam_type}</span>
          {report.laterality && <Badge tone="accent">{report.laterality === 'D' ? 'Direito' : 'Esquerdo'}</Badge>}
          <span className="text-[var(--color-ink-muted)]">{report.sex}, {report.age_at_exam} anos</span>
          <span className="text-[var(--color-ink-faint)]">{report.exam_datetime}</span>
        </div>
      </Card>

      {report.sections.map((section) => (
        <Card key={section.id} className="p-5">
          <div className="mb-3 flex items-center gap-2">
            <h3 className="text-sm font-semibold text-[var(--color-ink)]">
              {sectionLabels[section.section_type] ?? section.section_type}
            </h3>
            {section.unmatched_header && <Badge tone="warning">cabeçalho não reconhecido</Badge>}
          </div>
          <div className="space-y-2.5">
            {section.sentences.map((sent) => (
              <div key={sent.id}>
                <p className="text-sm leading-relaxed text-[var(--color-ink)]">{sent.text_raw}</p>
                {sent.concepts.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {sent.concepts.map((c) => (
                      <Badge key={c.id} tone={c.status === 'present' ? 'accent' : 'neutral'}>
                        {c.structure_label} · {c.finding_label} · {c.status_label}
                        {c.severity_label && ` · ${c.severity_label}`}
                        {c.location_label && ` · ${c.location_label}`}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  )
}
