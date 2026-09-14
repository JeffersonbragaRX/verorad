import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { PageHeader } from '../components/PageHeader'
import { Card, ErrorBanner, Spinner } from '../components/ui'

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs text-[var(--color-ink-muted)]">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-[var(--color-ink)]">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-[var(--color-ink-faint)]">{hint}</p>}
    </Card>
  )
}

function Bars({ data }: { data: Record<string, number> }) {
  const max = Math.max(...Object.values(data), 1)
  return (
    <div className="space-y-1.5">
      {Object.entries(data).map(([k, v]) => (
        <div key={k} className="flex items-center gap-2 text-xs">
          <span className="w-36 shrink-0 truncate text-[var(--color-ink-muted)]">{k}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--color-bg-subtle)]">
            <div
              className="h-full rounded-full bg-[var(--color-accent)]"
              style={{ width: `${(100 * v) / max}%` }}
            />
          </div>
          <span className="w-14 shrink-0 text-right tabular-nums text-[var(--color-ink)]">
            {v.toLocaleString('pt-BR')}
          </span>
        </div>
      ))}
    </div>
  )
}

export function Overview() {
  const { data, loading, error, reload } = useAsync(() => api.analysisOverview(), [])

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Visão geral do corpus"
        description="Mineração clínica sobre o corpus inteiro — todas as modalidades, domínios e tipos de exame."
      />
      <div className="flex-1 space-y-4 overflow-y-auto p-8">
        {loading && <Card className="p-8"><Spinner label="Carregando…" /></Card>}
        {error && <ErrorBanner message={error} onRetry={reload} />}

        {data && (
          <>
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
              <Tile label="Laudos" value={data.reports.toLocaleString('pt-BR')} />
              <Tile label="Pacientes" value={data.patients.toLocaleString('pt-BR')} hint="pseudônimos" />
              <Tile label="Sentenças" value={data.sentences.toLocaleString('pt-BR')} />
              <Tile label="Tipos de exame" value={String(data.exam_types)} />
              <Tile label="Conceitos clínicos" value={data.concepts.toLocaleString('pt-BR')} />
              <Tile label="Termos no léxico" value={data.lexicon_terms.toLocaleString('pt-BR')} />
              <Tile label="Médicos" value={String(data.doctors)} />
              <Tile label="Domínios" value={String(data.domains)} />
            </div>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
              <Card className="p-5">
                <h3 className="mb-3 text-sm font-semibold text-[var(--color-ink)]">Por modalidade</h3>
                <Bars data={data.by_modality} />
              </Card>
              <Card className="p-5">
                <h3 className="mb-3 text-sm font-semibold text-[var(--color-ink)]">Por domínio</h3>
                <Bars data={data.by_domain} />
              </Card>
              <Card className="p-5">
                <h3 className="mb-3 text-sm font-semibold text-[var(--color-ink)]">
                  Conceitos por status
                </h3>
                <Bars data={data.by_status} />
                <p className="mt-3 text-xs text-[var(--color-ink-faint)]">
                  "normal" é normalidade declarada explicitamente pelo médico — diferente de
                  estrutura não mencionada, que não gera conceito nenhum.
                </p>
              </Card>
            </div>

            <Card className="border-[var(--color-warning-border)] p-4">
              <p className="text-sm font-medium text-[var(--color-warning)]">
                Nenhum conteúdo desta camada está validado clinicamente.
              </p>
              <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
                {data.validation_note} Os números são padrões documentados neste corpus, não
                conhecimento médico. A promoção para validado depende da sua revisão.
              </p>
            </Card>
          </>
        )}
      </div>
    </div>
  )
}
