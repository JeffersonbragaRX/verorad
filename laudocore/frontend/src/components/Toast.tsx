import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'

interface ToastMessage {
  id: number
  kind: 'success' | 'error'
  text: string
}

interface ToastContextValue {
  notify: (kind: 'success' | 'error', text: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const nextId = useRef(0)

  const notify = useCallback((kind: 'success' | 'error', text: string) => {
    const id = nextId.current++
    setToasts((prev) => [...prev, { id, kind, text }])
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 3500)
  }, [])

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={
              'rounded-lg border px-4 py-2.5 text-sm shadow-[var(--shadow-soft-lg)] ' +
              (t.kind === 'success'
                ? 'border-[var(--color-success-border)] bg-[var(--color-success-subtle)] text-[var(--color-success)]'
                : 'border-[var(--color-danger-border)] bg-[var(--color-danger-subtle)] text-[var(--color-danger)]')
            }
          >
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast precisa estar dentro de <ToastProvider>')
  return ctx
}
