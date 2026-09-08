import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { PageHeader } from '../components/PageHeader'
import { Card, ErrorBanner, Skeleton } from '../components/ui'

export function Dashboard() {
  const { data: stats, loading, error, reload } = useAsync(() => api.stats(), [])

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Visão geral do vertical piloto — RM de joelho (RM_JOELHO_D / RM_JOELHO_E)."
      />
      <div className="mx-auto max-w-5xl px-8 py-6">
        {error && <ErrorBanner message={error} onRetry={reload} />}

        {loading && (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        )}

        {stats && (
          <>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <StatTile label="Laudos no vertical" value={stats.reports_total} />
              <StatTile label="Sentenças extraídas" value={stats.sentences_total} />
              <StatTile label="Conceitos clínicos" value={stats.concepts_total} />
              <StatTile
                label="Fila de revisão pendente"
                value={stats.review_queue_pending}
                href="/revisao"
                tone={stats.review_queue_pending > 0 ? 'warning' : 'default'}
              />
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <Card className="p-5">
                <h2 className="text-sm font-semibold text-[var(--color-ink)]">Fila de revisão por risco</h2>
                <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
                  Casos de ambiguidade clínica genuína, aguardando julgamento humano.
                </p>
                <div className="mt-4 space-y-2">
                  {(['high', 'medium', 'low'] as const).map((risk) => (
                    <RiskRow key={risk} risk={risk} count={stats.review_queue_by_risk[risk] ?? 0} />
                  ))}
                  {stats.review_queue_pending === 0 && (
                    <p className="text-sm text-[var(--color-ink-muted)]">Nenhum item pendente.</p>
                  )}
                </div>
                <Link
                  to="/revisao"
                  className="mt-4 inline-block text-sm font-medium text-[var(--color-accent)] hover:underline"
                >
                  Ver fila completa →
                </Link>
              </Card>

              <Card className="p-5">
                <h2 className="text-sm font-semibold text-[var(--color-ink)]">Cobertura do vertical</h2>
                <dl className="mt-4 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-[var(--color-ink-muted)]">Médicos</dt>
                    <dd className="font-medium">{stats.doctors.join(', ')}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-[var(--color-ink-muted)]">Tipos de exame</dt>
                    <dd className="font-medium">{stats.exam_types.join(', ')}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-[var(--color-ink-muted)]">Itens já revisados</dt>
                    <dd className="font-medium">{stats.review_queue_resolved}</dd>
                  </div>
                </dl>
                <Link
                  to="/laudo"
                  className="mt-4 inline-block text-sm font-medium text-[var(--color-accent)] hover:underline"
                >
                  Montar um laudo →
                </Link>
              </Card>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function StatTile({
  label, value, href, tone = 'default',
}: { label: string; value: number; href?: string; tone?: 'default' | 'warning' }) {
  const content = (
    <Card className={'p-4 ' + (tone === 'warning' && value > 0 ? 'border-[var(--color-warning-border)]' : '')}>
      <p className="text-xs font-medium text-[var(--color-ink-muted)]">{label}</p>
      <p
        className={
          'mt-1 text-2xl font-semibold ' +
          (tone === 'warning' && value > 0 ? 'text-[var(--color-warning)]' : 'text-[var(--color-ink)]')
        }
      >
        {value.toLocaleString('pt-BR')}
      </p>
    </Card>
  )
  return href ? <Link to={href}>{content}</Link> : content
}

function RiskRow({ risk, count }: { risk: 'high' | 'medium' | 'low'; count: number }) {
  const labels = { high: 'Risco alto', medium: 'Risco médio', low: 'Risco baixo' }
  const colors = { high: 'bg-[var(--color-danger)]', medium: 'bg-[var(--color-warning)]', low: 'bg-[var(--color-ink-faint)]' }
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="flex items-center gap-2 text-[var(--color-ink-muted)]">
        <span className={`h-2 w-2 rounded-full ${colors[risk]}`} />
        {labels[risk]}
      </span>
      <span className="font-medium text-[var(--color-ink)]">{count}</span>
    </div>
  )
}
