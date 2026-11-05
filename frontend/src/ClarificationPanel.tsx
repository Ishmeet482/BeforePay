import { useEffect, useRef, useState } from 'react'
import { request, type Category } from './review-api'
import { Action } from './product-ui'
import { friendlyError } from './conditions'

import SavedClarification from './SavedClarification'
import type { Suggestion } from './clarification-types'
export default function ClarificationPanel({ bookingId, comparisonId, fingerprint, category, blocked, refreshToken }: { refreshToken: number; bookingId: string; comparisonId: string; fingerprint: string; category: Category; blocked: boolean }) {
  const path = `/bookings/${bookingId}/comparisons/${comparisonId}/clarifications`
  const [items, setItems] = useState<Suggestion[]>([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [needsRefresh, setNeedsRefresh] = useState(false)
  const [serial, setSerial] = useState(0)
  const pending = useRef(false), revision = useRef(0), mounted = useRef(true)
  const staleSaved = items.some(item => item.stale)
  async function load(signal?: AbortSignal) {
    const epoch = revision.current
    const results = await request<Suggestion[]>(`${path}?category=${category}&limit=20`, { signal })
    if (signal?.aborted || !mounted.current) return
    setItems(results); setNeedsRefresh(epoch !== revision.current); setSerial(n => n + 1)
  }
  useEffect(() => {
    mounted.current = true
    const controller = new AbortController(); setLoading(true)
    const changed = () => { revision.current++; setNeedsRefresh(true) }
    window.addEventListener('contextkey:changed', changed)
    load(controller.signal).catch(e => { if (!controller.signal.aborted) { setError(e.message); setNeedsRefresh(true) } }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => { mounted.current = false; controller.abort(); window.removeEventListener('contextkey:changed', changed) }
  }, [path, category, refreshToken])
  async function refresh() {
    setLoading(true); setError('')
    try { await load() } catch (e) { setError(e instanceof Error ? e.message : 'Could not read saved suggestions.'); setNeedsRefresh(true) } finally { if (mounted.current) setLoading(false) }
  }
  async function generate() {
    if (pending.current || blocked || staleSaved || needsRefresh || loading) return
    pending.current = true; setGenerating(true); setError('')
    try {
      await request<Suggestion>(path, { method: 'POST', body: JSON.stringify({ comparison_fingerprint: fingerprint, category }), signal: AbortSignal.timeout(75000) })
      await load()
    } catch (e) {
      if (mounted.current) { setError(e instanceof Error ? e.message : 'Clarification request failed.'); setNeedsRefresh(true) }
    } finally { pending.current = false; if (mounted.current) setGenerating(false) }
  }
  function result(item: Suggestion) {
    const stale = blocked || needsRefresh || item.stale || item.comparison_id !== comparisonId || item.comparison_fingerprint !== fingerprint
    return <SavedClarification key={item.id} item={item} bookingId={bookingId} stale={stale} refreshToken={serial} />
  }
  return <section className="clarification-panel" aria-label="Advisory clarification" aria-busy={loading || generating}>
    <h4>Ask before agreeing</h4><p className="hint">Gemini may suggest a question using only this saved discrepancy. Advisory only: nothing is resolved, approved or sent to the merchant. Checkout stays blocked by the existing checks.</p>
    <div className="clarification-actions"><Action aria-label={`Suggest clarification for ${category.replaceAll("_", " ")}`} className="ai-button" disabled={blocked || staleSaved || needsRefresh || loading || generating} reason={generating ? 'Generating once; this may take up to a minute.' : loading ? 'Reading saved suggestions…' : blocked || staleSaved ? 'Refresh and review the current saved comparison; save any unsaved merchant edits first.' : 'Saved inputs changed or a request failed. Refresh suggestions before generating again.'} onClick={() => void generate()}>Suggest clarification</Action><button disabled={loading || generating} onClick={() => void refresh()}>Refresh suggestions</button></div>
    {needsRefresh && <p className="notice attention">Refresh saved suggestions to check whether their comparison and versions are still current.</p>}
    {error && <p role="alert" className="notice error">{friendlyError(error)} No automatic retry was attempted.</p>}
    {items[0] && result(items[0])}
    {items.length > 1 && <details><summary>Earlier suggestions · {items.length - 1}</summary>{items.slice(1).map(result)}</details>}
  </section>
}
