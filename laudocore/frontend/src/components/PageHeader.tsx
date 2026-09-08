import type { ReactNode } from 'react'

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[var(--color-border)] bg-white px-8 py-5">
      <div>
        <h1 className="text-lg font-semibold text-[var(--color-ink)]">{title}</h1>
        {description && <p className="mt-0.5 text-sm text-[var(--color-ink-muted)]">{description}</p>}
      </div>
      {action}
    </div>
  )
}
