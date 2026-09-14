import { NavLink, Outlet } from 'react-router-dom'

// Dois grupos deliberadamente separados: a ANALISE opera sobre o corpus
// inteiro (camada universal, 210 tipos de exame) e nao esta validada
// clinicamente; a LAUDAGEM e' o vertical piloto de RM de joelho. Misturar
// os dois na navegacao daria a impressao de que o laudador cobre tudo.
const NAV_GROUPS = [
  {
    label: 'Análise do corpus',
    items: [
      { to: '/', label: 'Visão geral', end: true, icon: DashboardIcon },
      { to: '/cobertura', label: 'Cobertura', end: false, icon: GridIcon },
      { to: '/conceitos', label: 'Conceitos', end: false, icon: TagIcon },
      { to: '/associacoes', label: 'Associações', end: false, icon: LinkIcon },
      { to: '/medicos', label: 'Médicos', end: false, icon: UsersIcon },
      { to: '/cauda', label: 'Cauda não modelada', end: false, icon: FlagIcon },
    ],
  },
  {
    label: 'Laudagem (piloto: RM joelho)',
    items: [
      { to: '/biblioteca', label: 'Biblioteca', end: false, icon: LibraryIcon },
      { to: '/laudo', label: 'Novo laudo', end: false, icon: DocIcon },
      { to: '/revisao', label: 'Fila de revisão', end: false, icon: FlagIcon },
    ],
  },
]

export function Layout() {
  return (
    <div className="flex h-screen bg-[var(--color-bg-subtle)]">
      <aside className="flex w-60 shrink-0 flex-col border-r border-[var(--color-border)] bg-white">
        <div className="flex items-center gap-2 px-5 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-accent)] text-sm font-semibold text-white">
            LC
          </div>
          <div>
            <p className="text-sm font-semibold leading-tight text-[var(--color-ink)]">LaudoCore</p>
            <p className="text-xs leading-tight text-[var(--color-ink-faint)]">8.402 laudos · 210 exames</p>
          </div>
        </div>
        <nav className="flex flex-col gap-4 px-3">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="flex flex-col gap-0.5">
              <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
                {group.label}
              </p>
              {group.items.map(({ to, label, end, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ' +
                    (isActive
                      ? 'bg-[var(--color-accent-subtle)] text-[var(--color-accent)]'
                      : 'text-[var(--color-ink-muted)] hover:bg-[var(--color-bg-subtle)] hover:text-[var(--color-ink)]')
                  }
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="mt-auto px-5 py-4 text-xs text-[var(--color-ink-faint)]">
          Dados locais — nenhuma informação sai desta máquina.
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}

function DashboardIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="4.5" rx="1.5" />
      <rect x="13.5" y="10.5" width="7" height="10" rx="1.5" />
      <rect x="3.5" y="13" width="7" height="7.5" rx="1.5" />
    </svg>
  )
}
function LibraryIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
      <path d="M4 4.5h4a2 2 0 012 2V20a1.6 1.6 0 00-1.6-1.6H4V4.5z" />
      <path d="M20 4.5h-4a2 2 0 00-2 2V20a1.6 1.6 0 011.6-1.6H20V4.5z" />
    </svg>
  )
}
function DocIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
      <path d="M6 3.5h8l4 4V19a1.5 1.5 0 01-1.5 1.5h-11A1.5 1.5 0 014 19V5A1.5 1.5 0 016 3.5z" />
      <path d="M14 3.5V8h4" />
      <path d="M8 12.5h8M8 15.5h8M8 9.5h3" />
    </svg>
  )
}
function FlagIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
      <path d="M5 3.5v17" />
      <path d="M5 4.5h11l-2.5 3.5L16 11.5H5" />
    </svg>
  )
}

function GridIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
      <rect x="3.5" y="3.5" width="17" height="17" rx="2" />
      <path d="M3.5 9.5h17M3.5 15h17M9.5 3.5v17M15 3.5v17" />
    </svg>
  )
}

function TagIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
      <path d="M3.5 11.5V4.5a1 1 0 0 1 1-1h7l8.5 8.5-8 8-8.5-8.5Z" />
      <circle cx="8" cy="8" r="1.4" />
    </svg>
  )
}

function LinkIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
      <path d="M10 13.5a4 4 0 0 0 5.7.4l2.6-2.6a4 4 0 0 0-5.7-5.7l-1.5 1.5" />
      <path d="M14 10.5a4 4 0 0 0-5.7-.4l-2.6 2.6a4 4 0 0 0 5.7 5.7l1.5-1.5" />
    </svg>
  )
}

function UsersIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 19.5c0-3 2.5-5 5.5-5s5.5 2 5.5 5" />
      <path d="M16 6.2a3 3 0 0 1 0 5.6M17.5 14.8c2 .6 3.3 2.3 3.3 4.7" />
    </svg>
  )
}
