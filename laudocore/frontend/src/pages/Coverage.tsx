import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { PageHeader } from '../components/PageHeader'
import { Badge, Card, EmptyState, ErrorBanner, Spinner } from '../components/ui'

const STATUS_TONE: Record<string, 'neutral' | 'warning' | 'danger' | 'success'> = {
  review_sample_pending: 'warning',
  processed_unvalidated: 'danger',
  low_sample: 'neutral',
  blocked_missing_data: 'danger',
  validated_textually: 'success',
  validated_clinically: 'success',
}

const STATUS_LABEL: Record<string, string> = {
  review_sample_pending: 'extraído, aguarda revisão',
  processed_unvalidated: 'cobertura baixa',
  low_sample: 'amostra pequena',
  blocked_missing_data: 'sem dado clínico',
  validated_textually: 'validado textualmente',
  validated_clinically: 'validado clinicamente',
}

export function Coverage() {
  const { data: rows, loading, error, reload } = useAsync(() => api.analysisCoverage(), [])
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [modality, setModality] = useState('')

  const filtered = useMemo(() => {
    if (!rows) return []
    return rows.filter((r) => {
      if (status && r.validation_status !== status) return false
      if (modality && r.modality !== modality) return false
      if (search && !`${r.exam_type} ${r.anatomy}`.toLowerCase().includes(search.toLowerCase()))
        return false
      return true
    })
  }, [rows, search, status, modality])

  const totals = useMemo(() => {
    if (!rows) return null
    const byStatus: Record<string, number> = {}
    let reports = 0
    for (const r of rows) {
      byStatus[r.validation_status] = (byStatus[r.validation_status] ?? 0) + 1
      reports += Number(r.reports)
    }
    return { byStatus, reports, types: rows.length }
  }, [rows])

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Matriz de cobertura"
        description="Uma linha por tipo de exame, com o nível de validação explícito. Nenhum tipo está validado clinicamente."
      />
      <div className="flex-1 space-y-4 overflow-y-auto p-8">
        {loading && <Card className="p-8"><Spinner label="Carregando matriz…" /></Card>}
        {error && <ErrorBanner message={error} onRetry={reload} />}

        {totals && (
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <Card className="p-4">
              <p className="text-xs text-[var(--color-ink-muted)]">Tipos de exame</p>
              <p className="mt-1 text-2xl font-semibold text-[var(--color-ink)]">{totals.types}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-[var(--color-ink-muted)]">Laudos cobertos</p>
              <p className="mt-1 text-2xl font-semibold text-[var(--color-ink)]">
                {totals.reports.toLocaleString('pt-BR')}
              </p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-[var(--color-ink-muted)]">Amostra pequena</p>
              <p className="mt-1 text-2xl font-semibold text-[var(--color-ink)]">
                {totals.byStatus['low_sample'] ?? 0}
              </p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-[var(--color-ink-muted)]">Validados clinicamente</p>
              <p className="mt-1 text-2xl font-semibold text-[var(--color-danger)]">0</p>
            </Card>
          </div>
        )}

        <Card className="p-4">
          <div className="flex flex-wrap gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filtrar por tipo de exame ou anatomia…"
              className="min-w-64 flex-1 rounded-lg border border-[var(--color-border-strong)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
            />
            <select
              value={modality}
              onChange={(e) => setModality(e.target.value)}
              className="rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm"
            >
              <option value="">Todas as modalidades</option>
              <option value="RM">RM</option>
              <option value="TC">TC</option>
              <option value="RX">RX</option>
            </select>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm"
            >
              <option value="">Todos os estados</option>
              {Object.keys(STATUS_LABEL).map((s) => (
                <option key={s} value={s}>{STATUS_LABEL[s]}</option>
              ))}
            </select>
          </div>
        </Card>

        {rows && filtered.length === 0 && (
          <EmptyState title="Nenhum tipo corresponde ao filtro" hint="Ajuste a busca." />
        )}

        {filtered.length > 0 && (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--color-border)] bg-[var(--color-bg-subtle)] text-left text-xs uppercase tracking-wide text-[var(--color-ink-faint)]">
                <tr>
                  <th className="px-4 py-2.5">Tipo de exame</th>
                  <th className="px-3 py-2.5">Mod.</th>
                  <th className="px-3 py-2.5 text-right">Laudos</th>
                  <th className="px-3 py-2.5 text-right">Pac.</th>
                  <th className="px-3 py-2.5 text-right">Méd.</th>
                  <th className="px-3 py-2.5 text-right">Cobertura</th>
                  <th className="px-3 py-2.5 text-right">Conceitos</th>
                  <th className="px-3 py-2.5 text-right">C/ estrutura</th>
                  <th className="px-4 py-2.5">Estado</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.exam_type} className="border-b border-[var(--color-border)] last:border-0">
                    <td className="px-4 py-2 font-medium text-[var(--color-ink)]">
                      {r.exam_type}
                      <span className="block text-xs text-[var(--color-ink-faint)]">{r.limitations}</span>
                    </td>
                    <td className="px-3 py-2 text-[var(--color-ink-muted)]">{r.modality}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.reports}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.patients}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.doctors}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.concept_coverage_pct}%</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.concepts}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.structure_binding_pct}%</td>
                    <td className="px-4 py-2">
                      <Badge tone={STATUS_TONE[r.validation_status] ?? 'neutral'}>
                        {STATUS_LABEL[r.validation_status] ?? r.validation_status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}

        <p className="pb-4 text-xs text-[var(--color-ink-faint)]">
          "Cobertura" aqui é superficial: mede se a sentença gerou ao menos um conceito.
          Não é recall clínico — isso exige a amostra anotada por radiologista.
        </p>
      </div>
    </div>
  )
}
