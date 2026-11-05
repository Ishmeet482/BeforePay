import { useContext, useEffect, useRef, useState } from 'react'
import { allPages } from './review-api'
import { friendlyError } from './conditions'
import { Resolve } from './product-ui'
import { WorkspaceReadContext } from './WorkspaceFrame'
import SavedClarification from './SavedClarification'
import type { Suggestion } from './clarification-types'
export default function MerchantClarifications({ bookingId, onBuyerReview }: { bookingId: string; onBuyerReview: () => void }) {
  const markRead = useContext(WorkspaceReadContext)
  const [items, setItems] = useState<Suggestion[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState(''), [needsRefresh, setNeedsRefresh] = useState(false), [serial, setSerial] = useState(0)
  const epoch = useRef(0)
  async function load(signal?: AbortSignal) {
    const version = epoch.current
    const records = await allPages<Suggestion>(`/bookings/${bookingId}/clarifications`, signal)
    if (signal?.aborted) return
    setItems(records); setNeedsRefresh(version !== epoch.current); setSerial(n => n + 1); markRead()
  }
  useEffect(() => {
    const c = new AbortController(), changed = () => { epoch.current++; setNeedsRefresh(true) }
    window.addEventListener('contextkey:changed', changed)
    load(c.signal).catch(e => { if (!c.signal.aborted) setError(e.message) }).finally(() => { if (!c.signal.aborted) setLoading(false) })
    return () => { c.abort(); window.removeEventListener('contextkey:changed', changed) }
  }, [bookingId])
  async function refresh() { setLoading(true); setError(''); try { await load() } catch (e) { setError(e instanceof Error ? e.message : 'Could not load questions.'); setNeedsRefresh(true) } finally { setLoading(false) } }
  const current = items.filter(s => !s.stale && s.output.status === 'suggested')
  return <section className="workspace merchant-clarifications" aria-busy={loading}><div className="toolbar"><div><h2>Clarification questions &amp; replies</h2><p>Read the exact saved terms, then append a provisional merchant response.</p></div><button disabled={loading} onClick={() => void refresh()}>Refresh questions &amp; replies</button></div><p className="notice">Merchant response—not verified resolution. Demo identity is provisional. Responses never change terms, approve agreements, resolve discrepancies or unblock checkout.</p>
    {error && <p className="notice error" role="alert">{friendlyError(error)}</p>}{needsRefresh && <p className="notice attention">Saved inputs changed. Refresh questions before relying on their current status. Unsaved reply drafts are retained.</p>}
    {!loading && !error && !current.length && <p>No current clarification questions to reply to. The buyer can explicitly request a question beside a saved comparison discrepancy.<button onClick={onBuyerReview}>Open Buyer comparison review →</button></p>}
    <Resolve label="Edit proposal as a new version" step="comparison" selector=".merchant-editor > summary" />
    {items.map(item => <details className="merchant-question" key={item.id} open={!item.stale && item.output.status === 'suggested'}><summary>{item.stale || needsRefresh || !!error ? 'Historical / context not current' : item.output.status === 'suggested' ? 'Current saved question' : 'Needs more information'} · {item.category.replaceAll('_', ' ')}</summary><SavedClarification item={item} bookingId={bookingId} stale={item.stale || needsRefresh || !!error} merchant refreshToken={serial} onSaved={() => void refresh()} /></details>)}
  </section>
}
