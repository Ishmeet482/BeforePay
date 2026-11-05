import { useEffect, useRef, useState } from 'react'
import { allPages, post } from './review-api'
import { Action, humanTime, Resolve, Status } from './product-ui'
import { friendlyError } from './conditions'
import TechnicalDetails from './TechnicalDetails'
import type { Suggestion } from './clarification-types'

type Reply = { id: string; merchant_label: string; response: string; identity_provisional: true; stale: boolean; stale_reasons: string[]; created_at: string; fingerprint: string }
export default function MerchantReplyThread({ bookingId, suggestion, stale, merchant, refreshToken, onSaved }: { bookingId: string; suggestion: Suggestion; stale: boolean; merchant: boolean; refreshToken: number; onSaved?: () => void }) {
  const path = `/bookings/${bookingId}/comparisons/${suggestion.comparison_id}/clarifications/${suggestion.id}/replies`
  const [replies, setReplies] = useState<Reply[]>([]), [label, setLabel] = useState(''), [response, setResponse] = useState('')
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState(''), [needsRefresh, setNeedsRefresh] = useState(false)
  const pending = useRef(false), mounted = useRef(true), epoch = useRef(0)
  const dirty = !!(label || response)
  useEffect(() => { if (!dirty) return; const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }; window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn) }, [dirty])
  async function load(signal?: AbortSignal) {
    const version = epoch.current
    const rows = await allPages<Reply>(path, signal)
    if (signal?.aborted || !mounted.current) return
    setReplies(rows); setNeedsRefresh(version !== epoch.current)
  }
  useEffect(() => {
    mounted.current = true
    const changed = () => { epoch.current++; setNeedsRefresh(true) }
    window.addEventListener('contextkey:changed', changed)
    return () => { mounted.current = false; window.removeEventListener('contextkey:changed', changed) }
  }, [])
  useEffect(() => {
    const c = new AbortController(); setLoading(true); setError('')
    load(c.signal).catch(e => { if (!c.signal.aborted) { setError(e.message); setNeedsRefresh(true) } }).finally(() => { if (!c.signal.aborted) setLoading(false) })
    return () => c.abort()
  }, [path, refreshToken])
  async function refresh() { setLoading(true); setError(''); try { await load() } catch (e) { setError(e instanceof Error ? e.message : 'Could not load merchant responses.'); setNeedsRefresh(true) } finally { if (mounted.current) setLoading(false) } }
  const invalidContext = stale || replies.some(r => r.stale) || !suggestion.proposal_id || !suggestion.proposal_fingerprint
  const blocked = invalidContext || needsRefresh || loading || saving
  async function save(e: React.FormEvent) {
    e.preventDefault()
    if (pending.current || blocked || !merchant || !label.trim() || !response.trim()) return
    pending.current = true; setSaving(true); setError(''); setMessage('')
    try {
      await post(path, { suggestion_fingerprint: suggestion.fingerprint, comparison_fingerprint: suggestion.comparison_fingerprint, proposal_id: suggestion.proposal_id, proposal_fingerprint: suggestion.proposal_fingerprint, merchant_label: label, response })
      if (!mounted.current) return
      setLabel(''); setResponse(''); setMessage('Merchant response saved. Terms and checkout eligibility are unchanged.')
      await load(); onSaved?.()
    } catch (e) { if (mounted.current) { setError(e instanceof Error ? e.message : 'Reply was not confirmed.'); setNeedsRefresh(true) } }
    finally { pending.current = false; if (mounted.current) setSaving(false) }
  }
  return <section className="merchant-reply-thread" aria-label="Merchant responses" aria-busy={loading || saving}>
    <div className="section-heading"><h4>Merchant responses</h4><button disabled={loading || saving} onClick={() => void refresh()}>Refresh replies</button></div>
    <p className="hint">Merchant response—not verified resolution. Labels are provisional, not authenticated identity. Replies do not amend terms, approve anything or unblock checkout.</p>
    {error && <p className="notice error" role="alert">{friendlyError(error)} Fields retained; refresh history before retrying. No automatic retry.</p>}
    {message && <p className="notice success" role="status">{message}</p>}
    {needsRefresh && <p className="notice attention">Saved context may have changed. Refresh replies and the question context before submitting.</p>}
    {!loading && !replies.length && <p className="hint">No merchant response recorded.</p>}
    {replies.map(reply => <article className="merchant-response" key={reply.id}><h4>Merchant response—not verified resolution</h4><Status tone={stale || needsRefresh || reply.stale ? 'attention' : 'neutral'}>{stale || needsRefresh || reply.stale ? 'Historical / context not current' : 'Current context at last refresh'}</Status><p className="hint">{reply.merchant_label} · provisional label · {humanTime(reply.created_at)}</p><p className="merchant-response-text">{reply.response}</p><TechnicalDetails label="Reply reference and context" data={{ reply_id: reply.id, fingerprint: reply.fingerprint, suggestion_id: suggestion.id, comparison_id: suggestion.comparison_id, proposal_id: suggestion.proposal_id, stale_reasons: reply.stale_reasons, identity_provisional: reply.identity_provisional }} /></article>)}
    {merchant && suggestion.output.status === 'suggested' && <form className="merchant-reply-form" onSubmit={e => void save(e)}><h4>Reply to this saved question</h4><fieldset disabled={blocked}><label>Merchant label (provisional)<input value={label} maxLength={100} onChange={e => setLabel(e.target.value)} /></label><label>Response text<textarea value={response} maxLength={5000} rows={4} onChange={e => setResponse(e.target.value)} /></label></fieldset><Action className="primary" disabled={blocked || !label.trim() || !response.trim()} reason={saving ? 'Saving this response once…' : loading ? 'Reading reply history…' : invalidContext ? 'This question’s saved context is outdated. A reply cannot be submitted against stale versions. Your draft is retained.' : needsRefresh ? 'Refresh the question context and reply history first.' : 'Enter a merchant label and nonblank response.'}>Save merchant response</Action><p className="hint">To change terms, save a new proposal through the versioned editor. This reply is a statement only.</p><Resolve label="Edit proposal as a new version" step="comparison" selector=".merchant-editor > summary" /></form>}
  </section>
}
