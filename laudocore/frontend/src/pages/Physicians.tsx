import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { PageHeader } from '../components/PageHeader'
import { Card, ErrorBanner, Spinner } from '../components/ui'

export function Physicians() {
  const { data, loading, error, reload } = useAsync(() => api.analysisPhysicians(), [])

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Estilo por médico"
        description="Perfil descritivo do corpus. Nenhum destes é o perfil Jefferson — esse só pode ser alimentado por correções que você aprovar."
      />
      <div className="flex-1 space-y-4 overflow-y-auto p-8">
        {loading && <Card className="p-8"><Spinner label="Carregando perfis…" /></Card>}
        {error && <ErrorBanner message={error} onRetry={reload} />}

        {data && (
          <>
            <Card className="overflow-x-auto p-0">
              <table className="w-full text-sm">
                <thead className="border-b border-[var(--color-border)] bg-[var(--color-bg-subtle)] text-left text-xs uppercase tracking-wide text-[var(--color-ink-faint)]">
                  <tr>
                    <th className="px-4 py-2.5">Médico</th>
                    <th className="px-3 py-2.5 text-right">Laudos</th>
                    <th className="px-3 py-2.5 text-right">Tipos de exame</th>
                    <th className="px-3 py-2.5 text-right">Conceitos/laudo</th>
                    <th className="px-3 py-2.5 text-right">Com impressão</th>
                    <th className="px-3 py-2.5 text-right">Negação</th>
                    <th className="px-3 py-2.5 text-right">Normalidade explícita</th>
                    <th className="px-4 py-2.5 text-right">Incerteza</th>
                  </tr>
                </thead>
                <tbody>
                  {data.comparison.map((r) => (
                    <tr key={r.doctor} className="border-b border-[var(--color-border)] last:border-0">
                      <td className="px-4 py-2 font-medium text-[var(--color-ink)]">{r.doctor}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.reports}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.exam_types_covered}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.concepts_per_report}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.pct_with_impression}%</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.pct_negated}%</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.pct_explicit_normality}%</td>
                      <td className="px-4 py-2 text-right tabular-nums">{r.pct_hedged}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {Object.entries(data.profiles).map(([doctor, p]) => (
                <Card key={doctor} className="p-5">
                  <h3 className="text-sm font-semibold text-[var(--color-ink)]">{doctor}</h3>
                  <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
                    {p.reports} laudos · {p.exam_types_covered} tipos de exame
                  </p>
                  <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
                    Achados mais frequentes
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {p.top_findings.slice(0, 10).map(([term, n]) => (
                      <span key={term} className="rounded-md bg-[var(--color-bg-subtle)] px-2 py-0.5 text-xs text-[var(--color-ink)]">
                        {term} <span className="text-[var(--color-ink-faint)]">{n}</span>
                      </span>
                    ))}
                  </div>
                  <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
                    Estruturas que declara normais
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {p.top_structures_declared_normal.slice(0, 8).map(([term, n]) => (
                      <span key={term} className="rounded-md bg-[var(--color-bg-subtle)] px-2 py-0.5 text-xs text-[var(--color-ink)]">
                        {term} <span className="text-[var(--color-ink-faint)]">{n}</span>
                      </span>
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
