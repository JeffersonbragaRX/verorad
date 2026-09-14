import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { PageHeader } from '../components/PageHeader'
import { Badge, Card, EmptyState, ErrorBanner, Spinner } from '../components/ui'

const STATUS_TONE: Record<string, 'neutral' | 'warning' | 'danger' | 'success'> = {
  present: 'warning', absent: 'neutral', normal: 'success',
}

export function Concepts() {
  const [finding, setFinding] = useState('')
  const [status, setStatus] = useState('')
  const [onlyConflicts, setOnlyConflicts] = useState(false)
  const { data, loading, error, reload } = useAsync(
    () => api.analysisConcepts({
      finding: finding || undefined, status: status || undefined,
      laterality_conflict: onlyConflicts, limit: 120,
    }),
    [finding, status, onlyConflicts],
  )

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Navegador de conceitos"
        description="Cada conceito com a sentença de origem ao lado — a proveniência faz parte do dado, não é um extra."
      />
      <div className="flex-1 space-y-4 overflow-y-auto p-8">
        <Card className="flex flex-wrap items-end gap-3 p-4">
          <input
            value={finding}
            onChange={(e) => setFinding(e.target.value)}
            placeholder="Filtrar por achado (ex.: tendinopatia)…"
            className="min-w-64 flex-1 rounded-lg border border-[var(--color-border-strong)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
          />
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm"
          >
            <option value="">Todos os status</option>
            <option value="present">presente</option>
            <option value="absent">ausente (negado)</option>
            <option value="normal">normalidade explícita</option>
          </select>
          <label className="flex items-center gap-2 pb-2 text-xs text-[var(--color-ink-muted)]">
            <input
              type="checkbox"
              checked={onlyConflicts}
              onChange={(e) => setOnlyConflicts(e.target.checked)}
            />
            só conflitos de lateralidade
          </label>
        </Card>

        {loading && <Card className="p-8"><Spinner label="Carregando conceitos…" /></Card>}
        {error && <ErrorBanner message={error} onRetry={reload} />}
        {data && data.length === 0 && (
          <EmptyState title="Nenhum conceito encontrado" hint="Ajuste os filtros." />
        )}

        <div className="space-y-2">
          {(data ?? []).map((c) => (
            <Card key={c.id} className="p-4">
              <div className="flex flex-wrap items-center gap-1.5">
                {c.structure && <Badge tone="neutral">{c.structure}</Badge>}
                {c.finding && <span className="text-sm font-medium text-[var(--color-ink)]">{c.finding}</span>}
                <Badge tone={STATUS_TONE[c.status] ?? 'neutral'}>{c.status}</Badge>
                {c.certainty !== 'definite' && <Badge tone="warning">{c.certainty}</Badge>}
                {c.laterality && (
                  <Badge tone={c.laterality_source === 'conflict' ? 'danger' : 'neutral'}>
                    {c.laterality}{c.laterality_source === 'conflict' ? ' (conflito)' : ''}
                  </Badge>
                )}
                {c.grade && <Badge tone="neutral">grau {c.grade}</Badge>}
                {c.severity && <Badge tone="neutral">{c.severity}</Badge>}
                {c.postoperative_context && <Badge tone="warning">{c.postoperative_context}</Badge>}
                {c.etiologic_qualifier && <Badge tone="neutral">{c.etiologic_qualifier}</Badge>}
              </div>

              <p className="mt-2 rounded-lg bg-[var(--color-bg-subtle)] p-3 text-sm leading-relaxed text-[var(--color-ink)]">
                {c.sentence_text}
              </p>

              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--color-ink-faint)]">
                <span>trecho: “{c.source_span}”</span>
                <span>{c.exam_type} · {c.doctor} · {c.section_type}</span>
                <span>regra: {c.rule_id}</span>
                <span>confiança: {c.confidence}</span>
                <span>validação: {c.validation_status}</span>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}
