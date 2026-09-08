import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { useToast } from '../components/Toast'
import { PageHeader } from '../components/PageHeader'
import { Badge, Button, Card, EmptyState, ErrorBanner, RiskBadge, Skeleton } from '../components/ui'
import type { ReviewQueueItem } from '../api/types'

const REASON_LABELS: Record<string, string> = {
  post_surgical_context: 'Contexto pós-cirúrgico/reconstrução',
  hedge_language: 'Linguagem de incerteza no texto original',
  multiple_measurements: 'Múltiplas medidas na sentença',
  grade_range_overflow: 'Faixa de grau com mais de 2 valores',
  unmatched_header: 'Cabeçalho de seção não reconhecido',
}

export function ReviewQueue() {
  const [status, setStatus] = useState('pending')
  const [riskLevel, setRiskLevel] = useState('')

  const { data: items, loading, error, reload } = useAsync(
    () => api.listReviewQueue({ status: status || undefined, risk_level: riskLevel || undefined }),
    [status, riskLevel],
  )

  return (
    <div>
      <PageHeader
        title="Fila de revisão clínica"
        description="Casos de ambiguidade genuína que o sistema não classificou sozinho — decisão fica com o médico."
      />
      <div className="mx-auto max-w-4xl space-y-4 px-8 py-6">
        <div className="flex gap-2">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
          >
            <option value="pending">Pendentes</option>
            <option value="resolved">Revisados</option>
            <option value="">Todos</option>
          </select>
          <select
            value={riskLevel}
            onChange={(e) => setRiskLevel(e.target.value)}
            className="rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
          >
            <option value="">Todos os riscos</option>
            <option value="high">Risco alto</option>
            <option value="medium">Risco médio</option>
            <option value="low">Risco baixo</option>
          </select>
        </div>

        {error && <ErrorBanner message={error} onRetry={reload} />}
        {loading && (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
          </div>
        )}
        {items && items.length === 0 && (
          <EmptyState
            title={status === 'pending' ? 'Nenhum item pendente' : 'Nenhum item encontrado'}
            hint={status === 'pending' ? 'Todos os casos de ambiguidade já foram revisados.' : undefined}
          />
        )}
        {items?.map((item) => (
          <ReviewItemCard key={item.id} item={item} onChanged={reload} />
        ))}
      </div>
    </div>
  )
}

function ReviewItemCard({ item, onChanged }: { item: ReviewQueueItem; onChanged: () => void }) {
  const { notify } = useToast()
  const [noteOpen, setNoteOpen] = useState(false)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  async function resolve() {
    setBusy(true)
    try {
      await api.resolveReviewItem(item.id, note || undefined)
      notify('success', 'Item marcado como revisado.')
      setNoteOpen(false)
      onChanged()
    } catch {
      notify('error', 'Não foi possível salvar a revisão.')
    } finally {
      setBusy(false)
    }
  }

  async function reopen() {
    setBusy(true)
    try {
      await api.reopenReviewItem(item.id)
      notify('success', 'Item reaberto.')
      onChanged()
    } catch {
      notify('error', 'Não foi possível reabrir o item.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center gap-2">
        <RiskBadge level={item.risk_level} />
        <Badge>{REASON_LABELS[item.reason] ?? item.reason}</Badge>
        <Badge tone="neutral">{item.doctor}</Badge>
        <Badge tone="neutral">{item.exam_type}</Badge>
        {item.status === 'resolved' && <Badge tone="success">Revisado</Badge>}
      </div>

      <p className="mt-3 rounded-lg bg-[var(--color-bg-subtle)] p-3 text-sm leading-relaxed text-[var(--color-ink)]">
        {item.original_text}
      </p>

      {item.system_output.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {item.system_output.map((c, i) => (
            <Badge key={i} tone="accent">
              {String(c.structure)} · {String(c.finding)} · {String(c.status)}
            </Badge>
          ))}
        </div>
      )}
      {item.rule_id && (
        <p className="mt-1.5 text-xs text-[var(--color-ink-faint)]">Regra: {item.rule_id}</p>
      )}

      {item.status === 'resolved' && item.reviewer_note && (
        <p className="mt-2 text-sm italic text-[var(--color-ink-muted)]">Nota: {item.reviewer_note}</p>
      )}

      <div className="mt-3 flex items-center gap-2">
        {item.status === 'pending' ? (
          noteOpen ? (
            <div className="flex flex-1 items-center gap-2">
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Nota de revisão (opcional)"
                className="flex-1 rounded-lg border border-[var(--color-border-strong)] px-3 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
                autoFocus
                onKeyDown={(e) => e.key === 'Enter' && resolve()}
              />
              <Button size="sm" onClick={resolve} disabled={busy}>Confirmar</Button>
              <Button size="sm" variant="ghost" onClick={() => setNoteOpen(false)}>Cancelar</Button>
            </div>
          ) : (
            <Button size="sm" onClick={() => setNoteOpen(true)}>Marcar como revisado</Button>
          )
        ) : (
          <Button size="sm" variant="secondary" onClick={reopen} disabled={busy}>Reabrir</Button>
        )}
      </div>
    </Card>
  )
}
