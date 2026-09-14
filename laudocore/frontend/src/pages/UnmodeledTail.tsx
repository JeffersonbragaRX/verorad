import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { PageHeader } from '../components/PageHeader'
import { Badge, Card, EmptyState, ErrorBanner, Spinner } from '../components/ui'

const PRIORITY_TONE: Record<string, 'danger' | 'warning' | 'neutral'> = {
  alta: 'danger', media: 'warning', baixa: 'neutral',
}

export function UnmodeledTail() {
  const [priority, setPriority] = useState('alta')
  const { data, loading, error, reload } = useAsync(
    () => api.analysisUnmodeledTail(priority || undefined),
    [priority],
  )

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Cauda não modelada"
        description="O vocabulário clínico que o léxico ainda não classifica. É lacuna medida e priorizada — não descartada."
      />
      <div className="flex-1 space-y-4 overflow-y-auto p-8">
        <Card className="flex flex-wrap items-center gap-3 p-4">
          <span className="text-xs text-[var(--color-ink-muted)]">Prioridade:</span>
          {['alta', 'media', 'baixa', ''].map((p) => (
            <button
              key={p || 'todas'}
              onClick={() => setPriority(p)}
              className={
                'rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ' +
                (priority === p
                  ? 'bg-[var(--color-accent-subtle)] text-[var(--color-accent)]'
                  : 'text-[var(--color-ink-muted)] hover:bg-[var(--color-bg-subtle)]')
              }
            >
              {p || 'todas'}
            </button>
          ))}
        </Card>

        {loading && <Card className="p-8"><Spinner label="Carregando cauda…" /></Card>}
        {error && <ErrorBanner message={error} onRetry={reload} />}
        {data && data.length === 0 && (
          <EmptyState title="Nada nesta prioridade" hint="Escolha outra faixa." />
        )}

        {data && data.length > 0 && (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--color-border)] bg-[var(--color-bg-subtle)] text-left text-xs uppercase tracking-wide text-[var(--color-ink-faint)]">
                <tr>
                  <th className="px-4 py-2.5">Termo</th>
                  <th className="px-3 py-2.5 text-right">Ocorrências</th>
                  <th className="px-3 py-2.5 text-right">Tipos de exame</th>
                  <th className="px-3 py-2.5">Mais frequente em</th>
                  <th className="px-3 py-2.5 text-right">P(prep)</th>
                  <th className="px-4 py-2.5">Por que não foi modelado</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r, i) => (
                  <tr key={i} className="border-b border-[var(--color-border)] last:border-0">
                    <td className="px-4 py-2 font-medium text-[var(--color-ink)]">
                      {r.term}{' '}
                      <Badge tone={PRIORITY_TONE[r.priority] ?? 'neutral'}>{r.priority}</Badge>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.frequency}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.n_exam_types}</td>
                    <td className="px-3 py-2 text-[var(--color-ink-muted)]">{r.top_exam_type}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.p_after_preposition}</td>
                    <td className="px-4 py-2 text-xs text-[var(--color-ink-muted)]">{r.reason_not_modeled}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  )
}
