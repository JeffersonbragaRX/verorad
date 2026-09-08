import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { useToast } from '../components/Toast'
import { PageHeader } from '../components/PageHeader'
import { Badge, Button, Card, EmptyState, ErrorBanner, Spinner } from '../components/ui'
import type { CompileResponse, FindingRequestIn, TaxonomyOption, TechniqueSuggestion } from '../api/types'

// Prefixos de aviso que representam risco clinico real (espelha
// backend/compiler/report_compiler.py:_BLOCKING_WARNING_PREFIXES) —
// usados so para destacar visualmente qual linha do painel de avisos
// e' a que esta' bloqueando copiar/exportar (a decisao de bloquear em
// si vem de result.blocking, calculado no backend).
const BLOCKING_WARNING_PREFIXES = ['CONTRADIÇÃO:', 'LATERALIDADE:']

interface SelectedFinding extends FindingRequestIn {
  key: string
  label: string
}

function optionLabel(o: TaxonomyOption): string {
  const parts = [o.structure_label, o.finding_label, o.status_label]
  if (o.severity_label) parts.push(o.severity_label)
  if (o.location_label) parts.push(o.location_label)
  return parts.join(' · ')
}

function optionKey(o: FindingRequestIn): string {
  return [o.structure, o.finding, o.status, o.severity ?? '', o.location ?? ''].join('|')
}

function normalize(text: string): string {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

/** Busca por todos os termos (em qualquer ordem, sem acento) — a label
 * usa ' · ' como separador entre estrutura/achado/status/gravidade, o
 * que uma busca por substring unica nao atravessaria. */
function matchesQuery(label: string, query: string): boolean {
  const terms = normalize(query).split(/\s+/).filter(Boolean)
  const haystack = normalize(label)
  return terms.every((t) => haystack.includes(t))
}

export function Compiler() {
  const { notify } = useToast()
  const searchRef = useRef<HTMLInputElement>(null)

  const { data: stats } = useAsync(() => api.stats(), [])
  const { data: taxonomy, loading: taxonomyLoading, error: taxonomyError, reload: reloadTaxonomy } =
    useAsync(() => api.taxonomy(), [])

  const [query, setQuery] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [selected, setSelected] = useState<SelectedFinding[]>([])
  const [doctor, setDoctor] = useState('')
  const [laterality, setLaterality] = useState('')
  const [techniqueText, setTechniqueText] = useState('')
  const [techniqueSuggestions, setTechniqueSuggestions] = useState<TechniqueSuggestion[] | null>(null)
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [indicationText, setIndicationText] = useState('')

  const [compiling, setCompiling] = useState(false)
  const [compileError, setCompileError] = useState<string | null>(null)
  const [result, setResult] = useState<CompileResponse | null>(null)

  const matches = useMemo(() => {
    if (!taxonomy) return []
    if (!query.trim()) return taxonomy.slice(0, 20)
    return taxonomy.filter((o) => matchesQuery(optionLabel(o), query)).slice(0, 30)
  }, [taxonomy, query])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === '/' && document.activeElement !== searchRef.current) {
        e.preventDefault()
        searchRef.current?.focus()
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        void handleCompile()
      }
      if (e.key === 'Escape') setPickerOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, doctor, laterality, techniqueText, indicationText])

  function addFinding(o: TaxonomyOption) {
    const candidate: FindingRequestIn = {
      structure: o.structure, finding: o.finding, status: o.status,
      severity: o.severity, location: o.location,
    }
    const key = optionKey(candidate)
    if (selected.some((s) => s.key === key)) {
      notify('error', 'Esse achado já foi adicionado.')
      return
    }
    setSelected((prev) => [...prev, { ...candidate, key, label: optionLabel(o) }])
    setQuery('')
    setPickerOpen(false)
  }

  function removeFinding(key: string) {
    setSelected((prev) => prev.filter((f) => f.key !== key))
  }

  async function handleCompile() {
    if (selected.length === 0) {
      notify('error', 'Adicione pelo menos um achado antes de compilar.')
      return
    }
    setCompiling(true)
    setCompileError(null)
    try {
      const res = await api.compile({
        findings: selected.map(({ structure, finding, status, severity, location }) => ({
          structure, finding, status, severity, location,
        })),
        doctor: doctor || null,
        laterality: laterality || null,
        technique_text: techniqueText.trim() || null,
        indication_text: indicationText || null,
      })
      setResult(res)
    } catch (err) {
      setCompileError(err instanceof Error ? err.message : 'Erro ao compilar o laudo.')
    } finally {
      setCompiling(false)
    }
  }

  async function handleLoadTechniqueSuggestions() {
    setLoadingSuggestions(true)
    try {
      const suggestions = await api.techniqueSuggestions(doctor || null)
      setTechniqueSuggestions(suggestions)
      if (suggestions.length === 0) notify('error', 'Nenhuma sugestão real encontrada no corpus.')
    } catch (err) {
      notify('error', err instanceof Error ? err.message : 'Erro ao buscar sugestões.')
    } finally {
      setLoadingSuggestions(false)
    }
  }

  async function handleCopy() {
    if (!result || result.blocking) return
    try {
      await navigator.clipboard.writeText(result.rendered_text)
      notify('success', 'Laudo copiado para a área de transferência.')
    } catch {
      notify('error', 'Não foi possível copiar automaticamente — selecione o texto manualmente.')
    }
  }

  function handleExport() {
    if (!result || result.blocking) return
    const blob = new Blob([result.rendered_text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `laudo_rm_joelho_${new Date().toISOString().slice(0, 10)}.txt`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    notify('success', 'Laudo exportado.')
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Novo laudo"
        description="Escolha os achados — o sistema escolhe a frase real do corpus para cada um. Nada é gerado livremente."
        action={
          <Button onClick={handleCompile} disabled={compiling || selected.length === 0} title="Ctrl/Cmd + Enter">
            {compiling ? 'Compilando…' : 'Compilar laudo'}
            <kbd className="ml-1 rounded border border-white/30 px-1 text-[10px] opacity-80">⌘⏎</kbd>
          </Button>
        }
      />

      <div className="grid flex-1 grid-cols-1 gap-6 overflow-y-auto p-8 xl:grid-cols-2">
        <div className="space-y-4">
          <Card className="p-5">
            <label className="text-sm font-semibold text-[var(--color-ink)]">Achados</label>
            <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
              Busque por estrutura, achado ou gravidade (ex.: "menisco medial rotura").
            </p>
            <div className="relative mt-3">
              <input
                ref={searchRef}
                value={query}
                onChange={(e) => { setQuery(e.target.value); setPickerOpen(true) }}
                onFocus={() => setPickerOpen(true)}
                placeholder="Buscar achado…"
                className="w-full rounded-lg border border-[var(--color-border-strong)] px-3 py-2 pr-10 text-sm outline-none focus:border-[var(--color-accent)]"
              />
              <kbd className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-[var(--color-border)] px-1.5 py-0.5 text-[10px] text-[var(--color-ink-faint)]">
                /
              </kbd>

              {pickerOpen && (
                <div className="absolute z-10 mt-1 max-h-80 w-full overflow-y-auto rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-soft-lg)]">
                  {taxonomyLoading && <div className="p-3"><Spinner label="Carregando achados…" /></div>}
                  {taxonomyError && <div className="p-3"><ErrorBanner message={taxonomyError} onRetry={reloadTaxonomy} /></div>}
                  {matches.length === 0 && !taxonomyLoading && (
                    <p className="p-3 text-sm text-[var(--color-ink-muted)]">Nenhum achado corresponde à busca.</p>
                  )}
                  {matches.map((o, idx) => (
                    <button
                      key={idx}
                      onClick={() => addFinding(o)}
                      className="flex w-full items-center justify-between gap-2 border-b border-[var(--color-border)] px-3 py-2 text-left text-sm last:border-0 hover:bg-[var(--color-bg-subtle)]"
                    >
                      <span>{optionLabel(o)}</span>
                      <span className="shrink-0 text-xs text-[var(--color-ink-faint)]">{o.frequency}×</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-4 space-y-2">
              {selected.length === 0 && (
                <EmptyState title="Nenhum achado selecionado" hint="Use a busca acima para adicionar achados ao laudo." />
              )}
              {selected.map((f) => (
                <div
                  key={f.key}
                  className="flex items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-subtle)] px-3 py-2"
                >
                  <span className="text-sm text-[var(--color-ink)]">{f.label}</span>
                  <button
                    onClick={() => removeFinding(f.key)}
                    aria-label={`Remover ${f.label}`}
                    className="rounded p-1 text-[var(--color-ink-faint)] hover:bg-[var(--color-bg-muted)] hover:text-[var(--color-danger)]"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </Card>

          <Card className="space-y-3 p-5">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm font-semibold text-[var(--color-ink)]">Médico (opcional)</label>
                <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
                  Usa a frase preferida desse médico quando ele já disse algo parecido.
                </p>
                <select
                  value={doctor}
                  onChange={(e) => setDoctor(e.target.value)}
                  className="mt-2 w-full rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
                >
                  <option value="">Sem preferência (mais frequente geral)</option>
                  {stats?.doctors.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
              <div>
                <label className="text-sm font-semibold text-[var(--color-ink)]">Lado do exame</label>
                <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
                  Evita reaproveitar frase de exame do lado oposto que nomeia o lado.
                </p>
                <select
                  value={laterality}
                  onChange={(e) => setLaterality(e.target.value)}
                  className="mt-2 w-full rounded-lg border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
                >
                  <option value="">Não informado</option>
                  <option value="D">Direito</option>
                  <option value="E">Esquerdo</option>
                </select>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="text-sm font-semibold text-[var(--color-ink)]">Técnica (opcional)</label>
                <button
                  type="button"
                  onClick={handleLoadTechniqueSuggestions}
                  disabled={loadingSuggestions}
                  className="text-xs font-medium text-[var(--color-accent)] hover:underline disabled:opacity-50"
                >
                  {loadingSuggestions ? 'Buscando…' : 'Sugerir do corpus'}
                </button>
              </div>
              <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
                Nunca preenchida sozinha — escreva a técnica deste exame ou escolha uma sugestão real abaixo.
              </p>
              <textarea
                value={techniqueText}
                onChange={(e) => setTechniqueText(e.target.value)}
                rows={2}
                placeholder="Ex.: Sequências FSE em múltiplos planos."
                className="mt-2 w-full resize-none rounded-lg border border-[var(--color-border-strong)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
              />
              {techniqueSuggestions && techniqueSuggestions.length > 0 && (
                <div className="mt-2 space-y-1">
                  {techniqueSuggestions.map((s, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => { setTechniqueText(s.text); setTechniqueSuggestions(null) }}
                      className="flex w-full items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-left text-xs hover:bg-[var(--color-bg-subtle)]"
                    >
                      <span className="text-[var(--color-ink)]">{s.text}</span>
                      <span className="shrink-0 text-[var(--color-ink-faint)]">{s.doctor} · {s.frequency}×</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div>
              <label className="text-sm font-semibold text-[var(--color-ink)]">Indicação clínica (opcional)</label>
              <textarea
                value={indicationText}
                onChange={(e) => setIndicationText(e.target.value)}
                rows={2}
                placeholder="Ex.: Dor no joelho."
                className="mt-2 w-full resize-none rounded-lg border border-[var(--color-border-strong)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
              />
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          {compileError && <ErrorBanner message={compileError} onRetry={handleCompile} />}

          {!result && !compiling && (
            <EmptyState
              title="Laudo ainda não compilado"
              hint="Adicione achados e clique em 'Compilar laudo' para ver o resultado aqui."
            />
          )}

          {compiling && <Card className="p-8"><Spinner label="Compilando laudo…" /></Card>}

          {result && !compiling && (
            <>
              {result.warnings.length > 0 && (
                <Card className={result.blocking ? 'border-[var(--color-danger-border)] p-4' : 'border-[var(--color-warning-border)] p-4'}>
                  <h3 className={result.blocking ? 'text-sm font-semibold text-[var(--color-danger)]' : 'text-sm font-semibold text-[var(--color-warning)]'}>
                    {result.blocking ? 'Revisão necessária antes de copiar ou exportar' : 'Avisos'}
                  </h3>
                  <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-[var(--color-ink)]">
                    {result.warnings.map((w, i) => {
                      const isBlocking = BLOCKING_WARNING_PREFIXES.some((p) => w.startsWith(p))
                      return <li key={i} className={isBlocking ? 'font-medium text-[var(--color-danger)]' : undefined}>{w}</li>
                    })}
                  </ul>
                </Card>
              )}

              {result.unresolved.length > 0 && (
                <Card className="border-[var(--color-danger-border)] p-4">
                  <h3 className="text-sm font-semibold text-[var(--color-danger)]">
                    Sem frase real no corpus ({result.unresolved.length})
                  </h3>
                  <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
                    Estes achados não foram incluídos no texto — não existe frase real correspondente.
                  </p>
                  <ul className="mt-2 space-y-1 text-sm text-[var(--color-ink)]">
                    {result.unresolved.map((f, i) => (
                      <li key={i}>{f.structure} · {f.finding} · {f.status}{f.severity ? ` · ${f.severity}` : ''}{f.location ? ` · ${f.location}` : ''}</li>
                    ))}
                  </ul>
                </Card>
              )}

              <Card className="p-5">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-[var(--color-ink)]">Laudo compilado</h3>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary" size="sm" onClick={handleCopy}
                      disabled={result.blocking}
                      title={result.blocking ? 'Resolva os avisos de revisão necessária antes de copiar' : undefined}
                    >
                      Copiar
                    </Button>
                    <Button
                      variant="secondary" size="sm" onClick={handleExport}
                      disabled={result.blocking}
                      title={result.blocking ? 'Resolva os avisos de revisão necessária antes de exportar' : undefined}
                    >
                      Exportar .txt
                    </Button>
                  </div>
                </div>
                {result.blocking && (
                  <p className="mb-3 text-xs font-medium text-[var(--color-danger)]">
                    Copiar e exportar estão desabilitados até os avisos acima serem revisados.
                  </p>
                )}
                <pre className="whitespace-pre-wrap rounded-lg bg-[var(--color-bg-subtle)] p-4 font-sans text-sm leading-relaxed text-[var(--color-ink)]">
                  {result.rendered_text}
                </pre>
              </Card>

              <Card className="p-5">
                <h3 className="text-sm font-semibold text-[var(--color-ink)]">Rastreabilidade</h3>
                <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
                  Cada frase usada, com o médico de origem e se foi um encaixe exato ou aproximado.
                </p>
                <div className="mt-3 space-y-2">
                  {result.findings_lines.map((rf, i) => (
                    <div key={i} className="flex items-start justify-between gap-2 border-b border-[var(--color-border)] pb-2 text-sm last:border-0">
                      <span className="text-[var(--color-ink)]">{rf.text}</span>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <Badge tone="neutral">{rf.source_doctor}</Badge>
                        {!rf.exact_match && <Badge tone="warning">aproximado</Badge>}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
