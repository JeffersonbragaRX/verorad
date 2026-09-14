import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { PageHeader } from '../components/PageHeader'
import { Badge, Card, EmptyState, ErrorBanner, Spinner } from '../components/ui'

export function Associations() {
  const [minDoctors, setMinDoctors] = useState(2)
  const [minEffect, setMinEffect] = useState(0.1)
  const [showArtifacts, setShowArtifacts] = useState(false)
  const { data, loading, error, reload } = useAsync(
    () => api.analysisAssociations({
      min_doctors: minDoctors, min_effect: minEffect,
      exclude_artifacts: !showArtifacts, limit: 300,
    }),
    [minDoctors, minEffect, showArtifacts],
  )

  const examTypes = useMemo(
    () => (data ? Array.from(new Set(data.map((r) => r.exam_type))).sort() : []),
    [data],
  )
  const [examFilter, setExamFilter] = useState('')
  const rows = useMemo(
    () => (data ?? []).filter((r) => !examFilter || r.exam_type === examFilter),
    [data, examFilter],
  )

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Associações entre achados"
        description="Coocorrência documentada neste corpus, com denominador, tamanho de efeito, IC e correção FDR. Não é causalidade nem conduta."
      />
      <div className="flex-1 space-y-4 overflow-y-auto p-8">
        <Card className="flex flex-wrap items-end gap-4 p-4">
          <label className="text-xs text-[var(--color-ink-muted)]">
            Mínimo de médicos
            <select
              value={minDoctors}
              onChange={(e) => setMinDoctors(Number(e.target.value))}
              className="mt-1 block rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm text-[var(--color-ink)]"
            >
              <option value={1}>1 (inclui hábito autoral)</option>
              <option value={2}>2 ou mais</option>
              <option value={3}>3 ou mais</option>
            </select>
          </label>
          <label className="text-xs text-[var(--color-ink-muted)]">
            Efeito mínimo (diferença absoluta)
            <select
              value={minEffect}
              onChange={(e) => setMinEffect(Number(e.target.value))}
              className="mt-1 block rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm text-[var(--color-ink)]"
            >
              <option value={0}>qualquer</option>
              <option value={0.1}>≥ 0,10</option>
              <option value={0.3}>≥ 0,30</option>
              <option value={0.5}>≥ 0,50</option>
            </select>
          </label>
          <label className="text-xs text-[var(--color-ink-muted)]">
            Tipo de exame
            <select
              value={examFilter}
              onChange={(e) => setExamFilter(e.target.value)}
              className="mt-1 block rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm text-[var(--color-ink)]"
            >
              <option value="">todos</option>
              {examTypes.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 pb-2 text-xs text-[var(--color-ink-muted)]">
            <input
              type="checkbox"
              checked={showArtifacts}
              onChange={(e) => setShowArtifacts(e.target.checked)}
            />
            mostrar artefatos de template
          </label>
        </Card>

        {loading && <Card className="p-8"><Spinner label="Calculando…" /></Card>}
        {error && <ErrorBanner message={error} onRetry={reload} />}
        {data && rows.length === 0 && (
          <EmptyState
            title="Nenhuma associação com esses critérios"
            hint="Reduza o efeito mínimo ou o número de médicos."
          />
        )}

        <div className="space-y-2">
          {rows.map((r, i) => (
            <Card key={i} className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium text-[var(--color-ink)]">{r.antecedent_concept}</span>
                  <span className="text-[var(--color-ink-faint)]">↔</span>
                  <span className="font-medium text-[var(--color-ink)]">{r.consequent_concept}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Badge tone="neutral">{r.exam_type}</Badge>
                  {r.mutually_locked_artifact === 'True' && (
                    <Badge tone="danger">artefato de template</Badge>
                  )}
                  {r.single_author_evidence === 'True' && (
                    <Badge tone="warning">autor único</Badge>
                  )}
                </div>
              </div>

              <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-[var(--color-ink-muted)] md:grid-cols-4">
                <span>P(B|A) <b className="text-[var(--color-ink)]">{r.p_b_given_a}</b> vs P(B|não A) <b className="text-[var(--color-ink)]">{r.p_b_without_a}</b></span>
                <span>diferença <b className="text-[var(--color-ink)]">{r.absolute_difference}</b></span>
                <span>RP <b className="text-[var(--color-ink)]">{r.prevalence_ratio}</b> [{r.pr_ci_low}–{r.pr_ci_high}]</span>
                <span>q = <b className="text-[var(--color-ink)]">{Number(r.q_value).toExponential(1)}</b></span>
                <span>n = {r.support_n} (bruto {r.support_n_without_dedup})</span>
                <span>denominador = {r.eligible_denominator}</span>
                <span>pacientes = {r.n_patients}</span>
                <span>médicos = {r.n_doctors} ({r.doctors})</span>
              </div>

              <p className="mt-2 border-t border-[var(--color-border)] pt-2 text-xs text-[var(--color-ink-faint)]">
                {r.interpretation_allowed}
              </p>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}
