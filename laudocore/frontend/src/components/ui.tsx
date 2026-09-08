// Primitivos de UI compartilhados — deliberadamente simples (sem
// biblioteca de componentes externa) para manter o app leve e sem
// dependencia de build extra, mantendo a estetica definida em index.css.
import type { ReactNode } from 'react'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={
        'rounded-xl border border-[var(--color-border)] bg-white shadow-[var(--shadow-soft)] ' +
        className
      }
    >
      {children}
    </div>
  )
}

export function Button({
  children, onClick, variant = 'primary', type = 'button', disabled, title, size = 'md',
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  type?: 'button' | 'submit'
  disabled?: boolean
  title?: string
  size?: 'sm' | 'md'
}) {
  const base =
    'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors ' +
    'disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-2 focus-visible:outline-[var(--color-accent)]'
  const sizes = size === 'sm' ? 'px-2.5 py-1.5 text-xs' : 'px-3.5 py-2 text-sm'
  const variants: Record<string, string> = {
    primary: 'bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)]',
    secondary:
      'bg-white text-[var(--color-ink)] border border-[var(--color-border-strong)] hover:bg-[var(--color-bg-subtle)]',
    ghost: 'text-[var(--color-ink-muted)] hover:bg-[var(--color-bg-muted)]',
    danger: 'bg-white text-[var(--color-danger)] border border-[var(--color-danger-border)] hover:bg-[var(--color-danger-subtle)]',
  }
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`${base} ${sizes} ${variants[variant]}`}
    >
      {children}
    </button>
  )
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'accent' | 'danger' | 'warning' | 'success' }) {
  const tones: Record<string, string> = {
    neutral: 'bg-[var(--color-bg-muted)] text-[var(--color-ink-muted)]',
    accent: 'bg-[var(--color-accent-subtle)] text-[var(--color-accent)]',
    danger: 'bg-[var(--color-danger-subtle)] text-[var(--color-danger)]',
    warning: 'bg-[var(--color-warning-subtle)] text-[var(--color-warning)]',
    success: 'bg-[var(--color-success-subtle)] text-[var(--color-success)]',
  }
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  )
}

export function RiskBadge({ level }: { level: string }) {
  const map: Record<string, { tone: 'danger' | 'warning' | 'neutral'; label: string }> = {
    high: { tone: 'danger', label: 'Risco alto' },
    medium: { tone: 'warning', label: 'Risco médio' },
    low: { tone: 'neutral', label: 'Risco baixo' },
  }
  const cfg = map[level] ?? { tone: 'neutral', label: level }
  return <Badge tone={cfg.tone}>{cfg.label}</Badge>
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-[var(--color-ink-muted)]" role="status">
      <svg className="h-4 w-4 animate-spin text-[var(--color-accent)]" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
      </svg>
      {label ?? 'Carregando…'}
    </div>
  )
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--color-border-strong)] bg-[var(--color-bg-subtle)] px-6 py-12 text-center">
      <p className="text-sm font-medium text-[var(--color-ink)]">{title}</p>
      {hint && <p className="max-w-sm text-sm text-[var(--color-ink-muted)]">{hint}</p>}
      {action}
    </div>
  )
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-[var(--color-danger-border)] bg-[var(--color-danger-subtle)] px-4 py-3 text-sm text-[var(--color-danger)]">
      <span>{message}</span>
      {onRetry && (
        <Button variant="danger" size="sm" onClick={onRetry}>
          Tentar de novo
        </Button>
      )}
    </div>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-[var(--color-bg-muted)] ${className}`} />
}
