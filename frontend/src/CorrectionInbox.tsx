import { useEffect, useState } from 'react'
import { allPages } from './review-api'
import type { Suggestion } from './clarification-types'
import CorrectionReview from './CorrectionReview'
import { friendlyError } from './conditions'

export default function CorrectionInbox({ bookingId, refreshToken }: { bookingId: string; refreshToken: number }) {
  const [items, setItems] = useState<Suggestion[]>([]), [error, setError] = useState(''), [busy, setBusy] = useState(true), [serial, setSerial] = useState(0)
  useEffect(() => { const c = new AbortController(); setBusy(true); allPages<Suggestion>(`/bookings/${bookingId}/clarifications`, c.signal).then(rows => { if (!c.signal.aborted) { setItems(rows); setSerial(n => n + 1); setError('') } }).catch(e => { if (!c.signal.aborted) setError(e.message) }).finally(() => { if (!c.signal.aborted) setBusy(false) }); return () => c.abort() }, [bookingId, refreshToken])
  async function refresh() { setBusy(true); setError(''); try { setItems(await allPages<Suggestion>(`/bookings/${bookingId}/clarifications`)); setSerial(n => n + 1) } catch (e) { setError(e instanceof Error ? e.message : 'Could not read clarification history.') } finally { setBusy(false) } }
  return <section className="correction-inbox" aria-busy={busy}><div className="section-heading"><h3>Clarifications &amp; correction history</h3><button disabled={busy} onClick={() => void refresh()}>Refresh clarification history</button></div><p className="hint">Original questions remain here after a corrected proposal and fresh comparison. Review corrections explicitly; recording review never approves checkout.</p>{error && <p className="notice error" role="alert">{friendlyError(error)}</p>}{!busy && !error && !items.length && <p className="hint">No saved clarification questions.</p>}{items.map(q => <article className="correction-question" key={q.id}><h4>{q.category.replaceAll('_', ' ')}</h4><p>{q.output.question || 'Needs more information; no supported question saved.'}</p><CorrectionReview bookingId={bookingId} suggestionId={q.id} buyer refreshToken={serial} /></article>)}</section>
}
