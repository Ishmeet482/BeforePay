import { useEffect, useRef, useState } from 'react'
import { allPages, post, request, type Citation, type Claim } from './review-api'
import { Action, describeClaim, EvidenceButton, humanTime, Status } from './product-ui'
import { friendlyError } from './conditions'
import TechnicalDetails from './TechnicalDetails'
import type { SupportingTerm } from './clarification-types'

const outcome = 'Correction reviewed for these versions—not checkout approval.'
type Reply = { id: string; merchant_label: string; response: string; created_at: string }
type Comparison = { id: string; stale: boolean; results: { category: string; status: string; agreement_terms: Claim[]; proposal_terms: Claim[] }[] }
type Context = { eligible: boolean; blockers: string[]; bindings: Record<string, string> | null; context_fingerprint: string | null; category: string; selected_reply_id: string | null; replies: Reply[]; original: { question: { question: string; explanation: string }; supporting_terms: SupportingTerm[]; proposal_version: number; comparison: Comparison }; corrected_proposal: { id: string; version: number; content: Record<string, Claim[]> } | null; comparison: Comparison | null }
type Review = { id: string; fingerprint: string; context_fingerprint: string; context: Context; reviewer_label: string; note: string; identity_provisional: true; created_at: string; stale: boolean; stale_reasons: string[] }
const missing: Record<string, string> = {
  affected_proposal_terms_unchanged: 'The newer proposal has not changed this question’s affected terms. The merchant must correct those saved terms first.',
  saved_merchant_reply_required: 'A saved merchant reply is required. Ask the merchant to reply in Clarification replies.',
  select_one_saved_merchant_reply: 'Several replies exist. Select the exact merchant statement you reviewed.',
  newer_merchant_proposal_and_comparison_required: 'The merchant must save a newer proposal; explicitly compare that proposal with the unchanged buyer agreement.',
  all_comparison_terms_must_match: 'The fresh comparison must match in every section. Resolve remaining differences and explicitly compare again.',
  missing_ambiguous_or_differing_terms: 'Saved terms remain missing, ambiguous or different. Correct them and compare again.',
  unchanged_buyer_baseline_and_confirmation_required: 'The buyer baseline or confirmation changed. This correction cannot be linked to the original question.',
}
function ContextSummary({ value: c, historical = false }: { value: Context; historical?: boolean }) {
  const originalResult = c.original.comparison.results.find(r => r.category === c.category)
  const result = c.comparison?.results.find(r => r.category === c.category)
  const selected = c.replies.find(r => r.id === c.selected_reply_id)
  return <div className="correction-context">
    <section><h4>Original discrepancy · proposal {c.original.proposal_version}</h4><p>{c.original.question.question}</p><p className="hint">{c.original.question.explanation}</p><div className="correction-terms">{c.original.supporting_terms.map(t => <div key={t.term_id}><strong>{t.side === 'agreement' ? 'Buyer-agreed term' : 'Original merchant term'}</strong><blockquote>{t.text}</blockquote>{!!t.citations.length && <EvidenceButton title="Original clarification support" citations={t.citations as Citation[]} />}</div>)}</div><details><summary>Full original comparison section</summary><div className="correction-terms"><h5>Buyer-agreed terms</h5>{originalResult?.agreement_terms.map((term, i) => <p className="term" key={i}>{describeClaim(term)}</p>)}<h5>Original merchant-proposed terms</h5>{originalResult?.proposal_terms.map((term, i) => <p className="term" key={i}>{describeClaim(term)}</p>)}</div></details></section>
    <section><h4>Merchant response—not verified resolution</h4>{selected ? <><p className="hint">{selected.merchant_label} · provisional label · {humanTime(selected.created_at)}</p><p className="merchant-response-text">{selected.response}</p></> : <p>No unambiguous merchant reply selected.</p>}</section>
    <section><h4>Corrected proposal{c.corrected_proposal ? ` · version ${c.corrected_proposal.version}` : ' · not available'}</h4>{(c.corrected_proposal?.content[c.category] || []).map((term, i) => <p className="term" key={i}>{describeClaim(term)}</p>)}</section>
    <section><h4>{historical ? 'Comparison at recorded review' : 'Fresh saved comparison'}</h4>{c.comparison ? <><Status tone={c.eligible ? 'success' : 'attention'}>{c.comparison.stale ? 'Outdated comparison' : c.eligible ? 'All affected and other sections match in this saved comparison' : 'Review blocked'}</Status><p>Affected section: {result?.status.replaceAll('_', ' ') || 'Missing result'}. Exact comparison and proposal references are bound below.</p><p className="hint">A saved comparison is not a guarantee of policy meaning.</p><details><summary>All comparison sections</summary><ul>{c.comparison.results.map((r, i) => <li key={i}>{r.category.replaceAll('_', ' ')}: {r.status.replaceAll('_', ' ')}</li>)}</ul></details></> : <p>No saved comparison available.</p>}</section>
    <TechnicalDetails label="Exact correction version bindings" data={c.bindings || {}} />
  </div>
}
export default function CorrectionReview({ bookingId, suggestionId, buyer = false, refreshToken = 0 }: { bookingId: string; suggestionId: string; buyer?: boolean; refreshToken?: number }) {
  const path = `/bookings/${bookingId}/clarifications/${suggestionId}`
  const [reviews, setReviews] = useState<Review[]>([]), [context, setContext] = useState<Context | null>(null)
  const [label, setLabel] = useState(''), [note, setNote] = useState(''), [busy, setBusy] = useState(false), [saving, setSaving] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState(''), [needsRefresh, setNeedsRefresh] = useState(false)
  const epoch = useRef(0), pending = useRef(false)
  useEffect(() => { const changed = () => { epoch.current++; setNeedsRefresh(true) }; window.addEventListener('contextkey:changed', changed); return () => window.removeEventListener('contextkey:changed', changed) }, [])
  useEffect(() => { const c = new AbortController(); allPages<Review>(path + '/correction-reviews', c.signal).then(rows => { if (!c.signal.aborted) setReviews(rows) }).catch(e => { if (!c.signal.aborted) setError(e.message) }); return () => c.abort() }, [path, refreshToken])
  useEffect(() => { if (!label && !note) return; const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }; window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn) }, [label, note])
  async function refresh(open: boolean, replyId?: string) {
    setBusy(true); setError(''); const version = epoch.current
    try { const rows = await allPages<Review>(path + '/correction-reviews'); setReviews(rows); if (open) setContext(await request<Context>(path + '/correction' + (replyId ? '?reply_id=' + encodeURIComponent(replyId) : ''))); setNeedsRefresh(version !== epoch.current) }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not read correction history.'); setNeedsRefresh(true) }
    finally { setBusy(false) }
  }
  const recorded = context && reviews.some(r => r.context_fingerprint === context.context_fingerprint)
  const blocked = busy || saving || needsRefresh || !!error || !context?.eligible || !context.bindings || recorded
  async function save(e: React.FormEvent) {
    e.preventDefault(); if (pending.current || blocked || !buyer || !label.trim() || !note.trim()) return
    pending.current = true; setSaving(true); setError(''); setMessage('')
    try { await post<Review>(path + '/correction-reviews', { bindings: context!.bindings, context_fingerprint: context!.context_fingerprint, reviewer_label: label, note }); setLabel(''); setNote(''); setMessage(outcome); await refresh(true, context?.selected_reply_id || undefined) }
    catch (e) { setError(e instanceof Error ? e.message : 'Review was not confirmed.'); setNeedsRefresh(true) }
    finally { pending.current = false; setSaving(false) }
  }
  return <section className="correction-review" aria-label="Correction review history" aria-busy={busy || saving}>
    <div className="clarification-actions">{buyer && <button disabled={busy || saving} onClick={() => void refresh(true, context?.selected_reply_id || undefined)}>{busy ? 'Reading correction…' : 'Review correction'}</button>}<button disabled={busy || saving} onClick={() => void refresh(!!context, context?.selected_reply_id || undefined)}>Refresh correction history</button></div>
    {error && <p className="notice error" role="alert">{friendlyError(error)} Inputs retained. Refresh before another explicit attempt; no automatic retry.</p>}{message && <p className="notice success" role="status">{message}</p>}
    {needsRefresh && <p className="notice attention">Saved context may have changed. Refresh correction history before recording a review.</p>}
    {buyer && context && <div className="correction-review-content"><p className="notice">Review the saved correction below. This records review for exact versions only; it does not approve checkout, cancellation rules or payment. Reviewer identity is provisional.</p>{context.replies.length > 1 && <label>Merchant reply reviewed<select disabled={busy || saving} value={context.selected_reply_id || ''} onChange={e => void refresh(true, e.target.value || undefined)}><option value="">Select one saved merchant reply</option>{context.replies.map((r, i) => <option key={r.id} value={r.id}>{r.merchant_label} · {humanTime(r.created_at)} · statement {i + 1}</option>)}</select></label>}
      <ContextSummary value={context} />{!!context.blockers.length && <div className="notice attention"><strong>Cannot record this correction yet</strong><ul>{context.blockers.map(b => <li key={b}>{missing[b] || friendlyError(b)}</li>)}</ul><p>Use the existing agreement/proposal editor and explicit comparison flow to correct saved terms. This review never creates a comparison.</p></div>}
      <form className="correction-review-form" onSubmit={e => void save(e)}><fieldset disabled={!!blocked}><label>Reviewer label (provisional)<input maxLength={100} value={label} onChange={e => setLabel(e.target.value)} /></label><label>Review note<textarea rows={3} maxLength={5000} value={note} onChange={e => setNote(e.target.value)} /></label></fieldset><Action className="primary" disabled={!!blocked || !label.trim() || !note.trim()} reason={recorded ? 'Correction review already recorded for these exact references. View the immutable history below.' : busy || saving ? 'Wait for the current read or save.' : needsRefresh || error ? 'Refresh correction history to recheck saved versions. Your inputs are retained.' : !context.eligible ? 'Resolve the listed saved-version requirements first.' : 'Enter a nonblank reviewer label and review note.'}>Record correction reviewed</Action></form>
    </div>}
    {!!reviews.length && <div className="correction-history"><h4>Recorded correction reviews</h4>{reviews.map(r => <article className="correction-record" key={r.id}><h4>{outcome}</h4><Status tone={r.stale || needsRefresh ? 'attention' : 'neutral'}>{r.stale || needsRefresh ? 'Outdated / refresh context' : 'Current for these versions at last refresh'}</Status><p className="hint">{r.reviewer_label} · provisional label · {humanTime(r.created_at)}</p><p className="merchant-response-text">{r.note}</p><details><summary>Reviewed discrepancy, reply and corrected versions</summary><ContextSummary value={r.context} historical /></details><TechnicalDetails label="Review record and stale reasons" data={{ id: r.id, fingerprint: r.fingerprint, stale_reasons: r.stale_reasons, identity_provisional: r.identity_provisional }} /></article>)}</div>}
    {!reviews.length && <p className="hint">No correction review recorded for this question.</p>}
  </section>
}
