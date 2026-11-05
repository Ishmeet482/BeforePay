import { BlockerContext } from './BlockerActions'
import { useContext, useEffect, useRef, useState } from 'react'
import { allPages, request } from './review-api'
import { Action, humanTime, Status } from './product-ui'
import { friendlyError } from './conditions'
import TechnicalDetails from './TechnicalDetails'

type Report = { id: string; model_metadata: Record<string, string> | null; proposal_id: string; proposal_version: number; proposal_fingerprint: string; status: string; stale: boolean; stale_reasons: string[]; created_at: string; fingerprint: string; clauses: { clause_id: string; category: string; text: string; ambiguous: boolean }[]; output: { findings: { status: string; explanation: string; references: { clause_id: string; quotation: string }[] }[] } }
type State = { proposal_id: string | null; proposal_fingerprint: string | null; blockers: string[] }
const names: Record<string, string> = { potential_contradiction: 'Potential contradiction', needs_clarification: 'Needs clarification', no_contradiction_found: 'No contradiction found' }
export default function PolicyConsistencyPanel({ bookingId, onState }: { bookingId: string; onState?: (state: State) => void }) {
  const { findingsSerial } = useContext(BlockerContext)
  const path = `/bookings/${bookingId}/policy-consistency`
  const [reports, setReports] = useState<Report[]>([]), [state, setState] = useState<State | null>(null), [busy, setBusy] = useState(true), [checking, setChecking] = useState(false), [error, setError] = useState(''), [changed, setChanged] = useState(false)
  const epoch = useRef(0), pending = useRef(false)
  async function load(signal?: AbortSignal) {
    const version = epoch.current
    const [rows, current] = await Promise.all([allPages<Report>(path, signal), request<State>(path + '/state', { signal })])
    if (signal?.aborted) return
    setReports(rows); setState(current); onState?.(current); setChanged(version !== epoch.current)
  }
  useEffect(() => { setBusy(true); setError(''); const c = new AbortController(), changed = () => { epoch.current++; setChanged(true) }; window.addEventListener('contextkey:changed', changed); load(c.signal).catch(e => { if (!c.signal.aborted) setError(e.message) }).finally(() => { if (!c.signal.aborted) setBusy(false) }); return () => { c.abort(); window.removeEventListener('contextkey:changed', changed) } }, [path, findingsSerial])
  async function refresh() { setBusy(true); setError(''); try { await load() } catch (e) { setError(e instanceof Error ? e.message : 'Could not read policy checks.'); setChanged(true) } finally { setBusy(false) } }
  async function check() {
    if (pending.current || busy || changed || !state?.proposal_id || checking || error) return
    pending.current = true; setChecking(true); setError('')
    try { await request<Report>(path, { method: 'POST', body: JSON.stringify({ proposal_id: state.proposal_id, proposal_fingerprint: state.proposal_fingerprint }), signal: AbortSignal.timeout(75000) }); await load() }
    catch (e) { setError(e instanceof Error ? e.message : 'Check was not confirmed.'); setChanged(true) }
    finally { pending.current = false; setChecking(false) }
  }
  const outdated = (r: Report) => r.stale || r.proposal_id !== state?.proposal_id || r.proposal_fingerprint !== state?.proposal_fingerprint
  function report(r: Report) { return <article className="consistency-report" key={r.id}><h4>{names[r.status]}</h4><Status tone={outdated(r) || changed ? 'attention' : r.status === 'no_contradiction_found' ? 'neutral' : 'blocked'}>{outdated(r) ? 'Outdated · historical proposal' : changed ? 'Refresh saved context' : `Saved merchant proposal ${r.proposal_version} · current at last refresh`}</Status><p className="hint">Recorded {humanTime(r.created_at)}. {r.model_metadata ? 'AI-assisted finding' : 'Saved-input completeness finding · no AI call'}, not policy approval or a guarantee.</p>{r.output.findings.map((f, i) => <section key={i}><strong>{names[f.status]}</strong><p>{f.explanation}</p>{f.references.map(ref => <details className="consistency-clause" key={ref.clause_id}><summary>{ref.clause_id.split(':')[0].replaceAll('_', ' ')} · exact supporting saved clause {Number(ref.clause_id.split(':')[1]) + 1}</summary><blockquote>{ref.quotation}</blockquote><p className="hint">Merchant-entered saved wording, not a verified source-document citation.</p></details>)}</section>)}<details><summary>All saved deposit and cancellation clauses</summary>{r.clauses.map(c => <div key={c.clause_id}><strong>{c.category.replaceAll('_', ' ')}</strong><blockquote>{c.text}</blockquote>{c.ambiguous && <p>Marked ambiguous in the saved proposal.</p>}</div>)}</details><TechnicalDetails label="Policy check references" data={{ check_id: r.id, fingerprint: r.fingerprint, proposal_id: r.proposal_id, proposal_fingerprint: r.proposal_fingerprint, stale_reasons: r.stale_reasons }} /></article> }
  const current = reports.filter(r => !outdated(r))
  return <section className="policy-consistency" aria-label="Saved merchant policy consistency" aria-busy={busy || checking}><div className="section-heading"><h3>Merchant policy consistency</h3><button disabled={busy || checking} onClick={() => void refresh()}>Refresh policy checks</button></div><p>Check all deposit and cancellation clauses together in the latest <strong>saved merchant proposal</strong>. Unsaved forms and buyer terms are not included. Gemini runs only when requested.</p><div className="clarification-actions"><Action className="ai-button" disabled={busy || checking || changed || !!error || !state?.proposal_id} reason={checking ? 'Checking once; allow up to a minute.' : busy ? 'Reading saved proposal and policy checks…' : changed || error ? 'Refresh policy checks to recheck the saved proposal before requesting another check.' : 'Save a merchant proposal through Final proposal first.'} onClick={() => void check()}>Check policy consistency</Action></div>
    {error && <p className="notice error" role="alert">{friendlyError(error)} No result was fabricated and no automatic retry was attempted.</p>}{changed && <p className="notice attention">Saved state may have changed. Refresh policy checks; old refund previews must be checked again.</p>}
    {!!state?.blockers.length && <p className="notice error">Current saved findings require clarification. Merchant refund outcomes and checkout are blocked server-side. A clean rerun cannot erase an unresolved finding; revise the proposal and explicitly check the new version.</p>}
    {!busy && !current.length && <p className="hint">No current policy check. Unchecked does not mean consistent. Existing review and payment guards still apply.</p>}
    <p className="hint">Compatible explicit exceptions can differ without contradiction. This check never selects precedence, calculates refunds or approves rules/checkout. Clean findings cannot override existing guards.</p>
    {current.map(report)}{!!reports.filter(outdated).length && <details><summary>Outdated policy-check history</summary>{reports.filter(outdated).map(report)}</details>}
  </section>
}
