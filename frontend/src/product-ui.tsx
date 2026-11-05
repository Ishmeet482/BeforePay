import { createContext, useContext, useEffect, useId, useRef, useState, type ReactNode } from 'react'
import type { Step } from './booking-state'
import { request, type Claim, type Citation, type Source } from './review-api'

export function money(amount?: string, currency?: string | null) {
  if (!amount || !currency) return 'Not specified'
  // Formatting only; all financial decisions and calculations belong to Python.
  return `${currency} ${amount}`
}
export function humanTime(value?: string | { local_datetime: string | null; timezone: string | null } | null): string {
  if (!value) return 'Not specified'
  if (typeof value === 'object') {
    if (!value.local_datetime) return `Unknown date · ${value.timezone || 'timezone missing'}`
    const localText = value.local_datetime.replace(/(?:Z|[+-]\d\d:\d\d)$/, '')
    const local = new Date(localText + 'Z')
    return `${Number.isNaN(local.valueOf()) ? value.local_datetime : new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }).format(local)} · ${value.timezone || 'timezone missing'}`
  }
  const d = new Date(value)
  return Number.isNaN(d.valueOf()) ? value : `${new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }).format(d)} · UTC`
}
export const amountNames: Record<string, string> = { rental_total: 'Rental fee', deposit: 'Deposit', total_payable: 'Inclusive total', tax: 'Tax', delivery: 'Delivery', other: 'Other' }
export function describeClaim(c: Claim) {
  if (c.kind) return `${amountNames[c.kind]} · ${money(c.amount, c.currency)}`
  if (c.name) return `${c.name} × ${c.quantity ?? 'quantity unknown'}`
  if (typeof c.value === 'object') return humanTime(c.value)
  return c.value || 'Not specified'
}
type Resolution = { label: string; step?: Step; selector?: string; run?: () => void }
export const JourneyContext = createContext<(step: Step, selector?: string) => void>(() => {})
export function focusTask(selector: string) {
  const target = document.querySelector<HTMLElement>(`.workspace-host:not([hidden]) ${selector}`)
  if (!target) return
  for (let parent: HTMLElement | null = target; parent; parent = parent.parentElement) if (parent instanceof HTMLDetailsElement) parent.open = true
  requestAnimationFrame(() => {
    target.scrollIntoView({ block: 'center', behavior: 'smooth' })
    if (!target.matches('input,textarea,select,button,summary,a')) target.tabIndex = -1
    target.focus({ preventScroll: true })
  })
}
export function Resolve({ label, step, selector, run }: Resolution) {
  const go = useContext(JourneyContext)
  return <button type="button" className="resolve-link" onClick={() => { if (run) { run(); requestAnimationFrame(() => { if (selector) focusTask(selector) }) } else if (step) go(step, selector); else if (selector) focusTask(selector) }}>{label} <span aria-hidden="true">→</span></button>
}
export function Action({ reason, resolve, children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { reason?: string; resolve?: Resolution; children: ReactNode }) {
  const id = useId()
  return <div className="action"><button {...props} aria-describedby={props.disabled && reason ? id : undefined}>{children}</button>{props.disabled && reason && <div className="action-guidance"><p className="action-explanation" id={id}>{reason}</p>{resolve && <Resolve {...resolve} />}</div>}</div>
}
export type Tone = 'neutral' | 'success' | 'attention' | 'blocked' | 'ai'
export function Status({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`status status-${tone}`}><span className="status-icon" aria-hidden="true">{tone === 'success' ? '✓' : tone === 'blocked' ? '!' : tone === 'attention' ? '!' : tone === 'ai' ? '✦' : '·'}</span>{children}</span>
}
export function TaskIntro({ owner, title, children }: { owner: string; title: string; children: ReactNode }) {
  return <div className="task-intro"><span className="ownership-label">{owner}</span><div><strong>{title}</strong><details className="task-context"><summary>How this step works</summary><p>{children}</p></details></div></div>
}

type Evidence = { citations: Citation[]; title: string; sourceId?: string; trigger?: HTMLElement }
const DrawerContext = createContext<(e: Evidence) => void>(() => {})
export function EvidenceButton({ citations, title = 'Supporting evidence', sourceId, children }: Evidence & { children?: ReactNode }) {
  const open = useContext(DrawerContext)
  return <button type="button" className="evidence-link" onClick={e => open({ citations, title, sourceId, trigger: e.currentTarget })}>{children || `View evidence${citations.length > 1 ? ` (${citations.length})` : ''}`}</button>
}
export function EvidenceProvider({ bookingId, children }: { bookingId: string; children: ReactNode }) {
  const [selection, setSelection] = useState<Evidence | null>(null)
  const [index, setIndex] = useState(0)
  const [source, setSource] = useState<Source | null>(null)
  const [error, setError] = useState('')
  const dialog = useRef<HTMLDialogElement>(null)
  const returnFocus = useRef<HTMLElement | null>(null)
  const titleId = useId()
  const cite = selection?.citations[index]
  const sourceId = cite?.source_id || selection?.sourceId
  useEffect(() => {
    if (!selection) return
    dialog.current?.showModal()
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previous }
  }, [selection])
  useEffect(() => {
    setSource(null); setError('')
    if (!sourceId) return
    const c = new AbortController()
    request<Source>(`/bookings/${bookingId}/sources/${sourceId}`, { signal: c.signal }).then(setSource).catch(e => { if (!c.signal.aborted) setError(e.message) })
    return () => c.abort()
  }, [sourceId, bookingId])
  function close() { dialog.current?.close() }
  function closed() { setSelection(null); requestAnimationFrame(() => { if (returnFocus.current?.isConnected) returnFocus.current.focus() }) }
  return <DrawerContext.Provider value={e => { returnFocus.current = e.trigger || (document.activeElement as HTMLElement); setIndex(0); setSelection(e) }}>{children}
    <dialog className="evidence-drawer" ref={dialog} aria-labelledby={titleId} onClose={closed}>
      <header><div><p className="eyebrow">ORIGINAL EVIDENCE</p><h2 id={titleId}>{selection?.title}</h2></div><button autoFocus onClick={close} aria-label="Close evidence">Close</button></header>
      {selection && selection.citations.length > 1 && <label>Supporting quotation<select value={index} onChange={e => setIndex(Number(e.target.value))}>{selection.citations.map((c, i) => <option key={i} value={i}>Quotation {i + 1}{c.page_number ? ` · page ${c.page_number}` : ''}</option>)}</select></label>}
      {cite && <section className="quoted-evidence"><h3>Exact quotation{cite.page_number ? ` · page ${cite.page_number}` : ''}</h3><blockquote>{cite.quotation}</blockquote></section>}
      {error && <p role="alert">Could not load source: {error}</p>}
      {sourceId && !source && !error && <p role="status">Loading source…</p>}
      {source && <><h3>{source.filename || source.source_type.replaceAll('_', ' ')}</h3><p className="hint">{source.medium === 'pdf' ? 'PDF source' : 'Original pasted text'}</p>{source.pages.length ? source.pages.map(p => <section className={p.page_number === cite?.page_number ? 'cited-page' : ''} key={p.page_number}><h4>Page {p.page_number}</h4><pre>{p.original_text}</pre></section>) : <pre>{source.original_text}</pre>}</>}
      {!sourceId && <p>No original-source citation. Customer-entered terms require their recorded correction reason.</p>}
    </dialog>
  </DrawerContext.Provider>
}
