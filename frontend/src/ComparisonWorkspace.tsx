import CorrectionInbox from './CorrectionInbox'
import ClarificationPanel from './ClarificationPanel'
import CategorySummary from './CategorySummary'
import { WorkspaceReadContext } from './WorkspaceFrame'
import TechnicalDetails from './TechnicalDetails'
import { Action, describeClaim, EvidenceButton, TaskIntro, Resolve, Status } from './product-ui'
import { useContext, useEffect, useState } from 'react'
import { allPages, categories, kinds, post, request, type Agreement, type Category, type Claim, type ReviewState } from './review-api'
import { blockerText, friendlyError, claim, row, titles, type Row } from './conditions'

type Content = Record<Category, Claim[]> & { included_items_none: boolean }
type Proposal = { id: string; version: number; fingerprint: string; content: Content; audit: { merchant_label: string; reason: string }; created_at: string }
type Result = { category: Category; status: 'matches' | 'differs' | 'needs_clarification'; basis: string; reason: string; agreement_terms: Claim[]; proposal_terms: Claim[]; agreement_quote: string | null; proposal_quote: string | null }
type Comparison = { id: string; agreement_id: string; agreement_fingerprint: string; proposal_id: string; proposal_fingerprint: string; fingerprint: string; stale: boolean; stale_reasons: string[]; results: Result[] }
type Rows = Record<Category, Row[]>
const empty = () => Object.fromEntries(categories.map(c => [c, [] as Row[]])) as Rows
const amountNames = { rental_total: 'Rental fee', total_payable: 'Total payable (inclusive)', deposit: 'Deposit', tax: 'Tax', delivery: 'Delivery', other: 'Other' }
function contentRows(content: Content): Rows { return Object.fromEntries(categories.map(c => [c, content[c].map(c => row({ origin: 'customer_entered', claim: c }))])) as Rows }
function baselineContent(a: Agreement): Content {
  return { ...Object.fromEntries(categories.map(c => [c, a.content.extraction[c].map((e): Claim => ({ ...e.claim, citations: [] }))])) as Record<Category, Claim[]>, included_items_none: a.content.explicit_none_categories.includes('included_items') }
}
const describe = describeClaim

export default function ComparisonWorkspace({ bookingId, view, onViewChange: setView }: { bookingId: string; view: 'buyer' | 'merchant'; onViewChange: (view: 'buyer' | 'merchant') => void }) {
  const markRead = useContext(WorkspaceReadContext)
  const base = `/bookings/${bookingId}`
  const [review, setReview] = useState<ReviewState | null>(null)
  const [baseline, setBaseline] = useState<Agreement | null>(null)
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [selected, setSelected] = useState<Proposal | null>(null)
  const [comparisons, setComparisons] = useState<Comparison[]>([])
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [rows, setRows] = useState<Rows>(empty)
  const [none, setNone] = useState(false)
  const [label, setLabel] = useState('')
  const [reason, setReason] = useState('')
  const [readSerial, setReadSerial] = useState(0)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [conflict, setConflict] = useState(false)
  async function load(signal?: AbortSignal, proposalId?: string) {
    const [r, p, c] = await Promise.all([
      request<ReviewState>(`${base}/review`, { signal }), allPages<Proposal>(`${base}/merchant-bookings`, signal),
      request<Comparison[]>(`${base}/comparisons?limit=20`, { signal }),
    ])
    const a = r.agreement_id ? await request<Agreement>(`${base}/agreements/${r.agreement_id}`, { signal }) : null
    if (signal?.aborted) return
    setReview(r); setBaseline(a); setProposals(p); setComparisons(c); setComparison(c[0] ?? null)
    const chosen = p.find(x => x.id === proposalId) ?? p[0] ?? null
    setSelected(chosen); setRows(chosen ? contentRows(chosen.content) : empty()); setNone(chosen?.content.included_items_none ?? false)
    setDirty(false); setConflict(false); setReadSerial(n => n + 1); markRead()
  }
  useEffect(() => {
    const controller = new AbortController(); setBusy(true)
    load(controller.signal).catch(e => { if (!controller.signal.aborted) setError(e.message) }).finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
    // One instance per booking retains proposal fields across prototype views.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
  async function act(work: () => Promise<void>) {
    setBusy(true); setError(''); setMessage('')
    try { await work() } catch (e) { setError(e instanceof Error ? e.message : 'Request failed.'); if (e instanceof Error && 'status' in e && e.status === 409) setConflict(true) }
    finally { setBusy(false) }
  }
  function change(cat: Category, next: Row[]) { setRows(old => ({ ...old, [cat]: next })); setDirty(true); setMessage('') }
  function edit(cat: Category, key: string, field: keyof Row, value: string | boolean) { change(cat, rows[cat].map(r => r.key === key ? { ...r, [field]: value } : r)) }
  function sample(which: 'mismatch' | 'matching' | 'equivalent' | 'contradictory') {
    if (!baseline || !review?.confirmation_current) return
    if (dirty && !window.confirm(which === 'matching' ? 'Replace unsaved proposal fields with buyer-confirmed terms?' : 'Replace unsaved proposal fields with this labelled sample?')) return
    const content = baselineContent(baseline)
    if (which === 'mismatch' || which === 'contradictory') {
      content.amounts = [
        { kind: 'rental_total', label: 'Rental fee', amount: '120.00', currency: 'USD', ambiguous: false, citations: [] },
        { kind: 'deposit', label: 'Deposit', amount: '80.00', currency: 'USD', ambiguous: false, citations: [] },
        { kind: 'total_payable', label: 'Total payable', amount: '200.00', currency: 'USD', ambiguous: false, citations: [] },
      ]
      content.currency = [{ value: 'USD', ambiguous: false, citations: [] }]
      content.deposit_conditions = [{ value: 'The USD 80 deposit is non-refundable.', ambiguous: false, citations: [] }]
      content.cancellation_conditions = (which === 'contradictory' ? [
        'Cancellation at least 48 hours before pickup gives a full refund of USD 200.',
        'Cancellation less than 48 hours before pickup refunds the deposit USD 80 and retains the rental fee USD 120.',
      ] : [
        'Cancellation at least 48 hours before pickup refunds the rental fee USD 120 only; the non-refundable deposit USD 80 is retained.',
        'Cancellation less than 48 hours before pickup retains the rental fee USD 120 and the non-refundable deposit USD 80; refund USD 0.',
      ]).map(value => ({ value, ambiguous: false, citations: [] }))
    }
    if (which === 'equivalent') {
      // Retain every clause unchanged and change only their textual presentation.
      // Gemini must still judge equivalence; the sample label is not a result.
      for (const category of ['deposit_conditions', 'cancellation_conditions'] as const) {
        const clauses = content[category]
        if (clauses.length) content[category] = [{ value: clauses.map(c => typeof c.value === 'string' ? c.value : '').join('\n\n'), ambiguous: clauses.some(c => c.ambiguous), citations: [] }]
      }
      // An explicit generic restatement keeps the original clauses in full.
      if (content.deposit_conditions.length) content.deposit_conditions[0].value = `Deposit terms apply as follows:\n${content.deposit_conditions[0].value}`
      if (content.cancellation_conditions.length) content.cancellation_conditions[0].value = `Cancellation terms apply as follows:\n${content.cancellation_conditions[0].value}`
    }
    setRows(contentRows(content)); setNone(content.included_items_none); setDirty(true)
    setMessage(which === 'matching' ? 'Buyer-confirmed terms copied into editable fields. Check against the final merchant booking; this is not merchant confirmation. Nothing saved or compared.' : `Sample loaded: ${which}. Form only; nothing saved, compared or confirmed.`)
  }
  async function save() {
    await act(async () => {
      const content = { ...Object.fromEntries(categories.map(c => [c, rows[c].map(r => claim(c, r))])), included_items_none: none }
      const next = await post<Proposal>(`${base}/merchant-bookings`, { expected_latest_id: proposals[0]?.id ?? null, merchant_label: label, reason, content })
      await load(undefined, next.id); setMessage(`Merchant booking version ${next.version} saved. Customer confirmation is unchanged. Click Compare explicitly.`)
    })
  }
  async function compare() {
    if (!baseline || !selected) return
    await act(async () => {
      const result = await request<Comparison>(`${base}/comparisons`, { method: 'POST', body: JSON.stringify({ agreement_id: baseline.id, agreement_fingerprint: baseline.fingerprint, proposal_id: selected.id, proposal_fingerprint: selected.fingerprint }), signal: AbortSignal.timeout(75000) })
      setComparison(result); setComparisons(old => [result, ...old]); setMessage('Comparison saved. This does not approve the merchant booking or authorize payment.')
    })
  }
  const currentProposal = selected?.id === proposals[0]?.id
  return <section className="workspace" aria-busy={busy}>
    <div className="toolbar"><div><h2>{view === 'buyer' ? 'Booking differences' : 'Merchant proposal'}</h2><p>Customer-confirmed terms stay separate from merchant proposals.</p></div><button disabled={busy} onClick={() => { if (!dirty || window.confirm('Discard unsaved fields and refresh?')) void act(() => load()) }}>Refresh</button></div>
    {busy && <p role="status">Loading / saving / comparing… Policy comparison may take up to a minute.</p>}
    {error && <div className="notice error" role="alert">{friendlyError(error)}{friendlyError(error) !== error && <TechnicalDetails label="Error details" data={{ error }} />}{conflict && <p>Inputs changed. Refresh before saving or comparing again.</p>}</div>}
    {message && <p className="notice success" role="status">{message}</p>}
    <div className="prototype-switch"><div><strong>Prototype view switch</strong><small>Same saved booking. Prototype views—not authenticated accounts.</small></div><div role="group" aria-label="Prototype workspace view"><button aria-pressed={view === 'buyer'} onClick={() => setView('buyer')}>Buyer · review differences</button><button aria-pressed={view === 'merchant'} onClick={() => setView('merchant')}>Merchant · edit proposal</button></div></div>
    <TaskIntro owner={view === 'buyer' ? 'Buyer review' : 'Merchant proposal'} title={view === 'buyer' ? 'What changed from the buyer-agreed terms?' : 'Prepare the merchant’s final booking'}>{view === 'buyer' ? 'Differences below describe saved versions. A matching total alone does not mean terms match.' : 'Edit an independent proposal beside the buyer baseline. Saving creates a merchant version; comparison is a separate explicit action.'}</TaskIntro>
    {!review?.confirmation_current && <p className="notice">Confirm a complete current agreement in Agreement review first. Merchant proposals can be saved independently; comparisons require a current confirmation.<Resolve label="Review buyer agreement" step="review" /></p>}
    {baseline && <div className="version-meta"><span className="badge">{review?.confirmation_current ? 'Buyer baseline · confirmed' : 'Buyer baseline · review required'}</span><span>Agreement version {baseline.version}</span><TechnicalDetails data={{ agreement_id: baseline.id, fingerprint: baseline.fingerprint }} /></div>}
    <div hidden={view !== 'buyer'} className="buyer-comparison">{comparison ? <ComparisonResults refreshToken={readSerial} bookingId={bookingId} blocked={busy || !review?.confirmation_current || conflict || comparison.id !== comparisons[0]?.id} comparison={comparison} dirty={dirty} onEdit={() => setView('merchant')} /> : <section className="comparison-empty"><h2>See what changed before you agree.</h2><p>No saved comparison yet. Save a final merchant booking, then explicitly compare it with your confirmed terms.</p></section>}
    <CorrectionInbox bookingId={bookingId} refreshToken={readSerial} />
    <section className="panel compare-action"><p className="eyebrow ai-label">✦ POLICY COMPARISON MAY USE GEMINI</p><h2>Compare saved versions</h2><p>Compare the saved booking with your confirmed agreement. Policy wording may be sent to Gemini only when you click Compare.</p><Action className="primary" disabled={busy || conflict || dirty || !currentProposal || !review?.confirmation_current || !selected} resolve={!busy && !conflict ? !review?.confirmation_current ? { label: 'Review buyer agreement', step: 'review' } : dirty || !selected || !currentProposal ? { label: 'Open merchant proposal', run: () => setView('merchant'), selector: '.merchant-editor > summary' } : undefined : undefined} reason={busy ? 'Wait for the current request.' : conflict ? 'Refresh stale inputs first.' : dirty ? 'Save merchant edits before comparing.' : !review?.confirmation_current ? 'Confirm the current customer agreement first.' : !selected ? 'Save a merchant booking first.' : 'Select the latest merchant version.'} onClick={() => void compare()}>Compare bookings · may use AI</Action></section>
    {!!comparisons.length && <label>Saved comparison<select value={comparison?.id ?? ''} disabled={busy} onChange={e => setComparison(comparisons.find(c => c.id === e.target.value) ?? null)}>{comparisons.map((c, index) => <option key={c.id} value={c.id}>Saved comparison {comparisons.length - index}{c.stale ? ' · stale' : ' · current at last refresh'}</option>)}</select></label>}
    <button className="edit-proposal-entry" onClick={() => setView('merchant')}>Open merchant proposal workspace →</button></div>
    <div hidden={view !== 'merchant'} className="merchant-view"><details className="merchant-editor" open={view === 'merchant'}><summary>Merchant editing workspace · {selected ? `saved version ${selected.version}` : 'add final booking'}{dirty ? ' · unsaved edits' : ''}</summary><p className="prototype-note">Prototype editing workspace, not an authenticated merchant role. Saving never changes the customer-confirmed agreement.</p>
    <section className="merchant-start"><h3>Start with the agreed terms. Check the final booking.</h3><Action disabled={busy || !review?.confirmation_current} reason={busy ? 'Wait for the current request.' : 'Confirm the current buyer agreement before copying its terms.'} resolve={!busy && !review?.confirmation_current ? { label: 'Review buyer agreement', step: 'review' } : undefined} onClick={() => sample('matching')}>Copy buyer-confirmed terms into form</Action><p className="hint">Fills fields only. Verify every merchant condition before saving; copying does not establish merchant agreement.</p></section>
    <details className="sample-tools"><summary>Demo samples · fill fields only</summary><section className="panel"><h3>Sample proposals</h3><p>Load a sample into the form, then save and compare when ready.</p><div className="sample-buttons">
      <button disabled={busy || !review?.confirmation_current} onClick={() => sample('mismatch')}>Sample: USD 200 total, non-refundable deposit</button>
      
      <button disabled={busy || !review?.confirmation_current} onClick={() => sample('equivalent')}>Sample: equivalent policy wording</button>
      <button disabled={busy || !review?.confirmation_current} onClick={() => sample('contradictory')}>Sample: contradictory deposit / cancellation · needs clarification</button>
    </div><details className="help"><summary>How samples work</summary><p>Samples only fill fields. Matching and equivalent samples use the confirmed terms. The non-refundable sample retains the deposit; the contradictory sample intentionally includes conflicting refunds. Loading never saves, compares or rewrites a proposal.</p></details></section></details>
    {!!proposals.length && <label>Saved merchant version<select disabled={busy} value={selected?.id ?? ''} onChange={e => {
      if (dirty && !window.confirm('Discard unsaved form and open this saved merchant version?')) return
      const p = proposals.find(v => v.id === e.target.value) ?? null
      setSelected(p); setRows(p ? contentRows(p.content) : empty()); setNone(p?.content.included_items_none ?? false); setDirty(false)
    }}>{proposals.map(p => <option key={p.id} value={p.id}>Version {p.version}{p.id === proposals[0]?.id ? ' · latest' : ' · historical'} · {p.audit.merchant_label}</option>)}</select></label>}
    {selected && <TechnicalDetails data={{ proposal_id: selected.id, fingerprint: selected.fingerprint }} />}
    {categories.map(cat => <section className="panel" key={cat}><h3>{titles[cat]}</h3><div className="comparison-columns"><div><p className="eyebrow">{review?.confirmation_current ? 'BUYER-AGREED · CONFIRMED' : 'BUYER BASELINE · NOT CURRENTLY CONFIRMED'}</p>{baseline ? <CategorySummary category={cat} rows={baseline.content.extraction[cat].map((e, index) => ({ ...row(e), key: `${baseline.id}-${cat}-${index}` }))} noItems={baseline.content.explicit_none_categories.includes(cat)} /> : <p>Unknown — no current confirmed agreement.</p>}</div>
      <fieldset disabled={busy || conflict}><legend>Merchant booking fields</legend>
        {cat === 'amounts' && <p className="hint">Total payable is inclusive, never an extra charge. No totals are calculated.</p>}
        {!rows[cat].length && <p className="hint">{cat === 'included_items' && none ? 'Explicitly no included items.' : 'Missing / unknown'}</p>}
        {rows[cat].map((r, i) => <div className="claim-row" key={r.key}><div className="claim-heading"><small>Merchant condition {i + 1}</small><button className="text-button" aria-label={`Remove merchant ${titles[cat]} row ${i + 1}`} onClick={() => change(cat, rows[cat].filter(x => x.key !== r.key))}>Remove</button></div>
          {(cat === 'equipment' || cat === 'included_items') && <div className="fields"><Input label="Item" value={r.name} change={v => edit(cat, r.key, 'name', v)} /><Input label="Quantity" value={r.quantity} change={v => edit(cat, r.key, 'quantity', v)} /></div>}
          {(cat === 'pickup' || cat === 'return_time') && <><Input label="Local date & time (ISO)" value={r.value} change={v => edit(cat, r.key, 'value', v)} /><Input label="Explicit timezone" value={r.timezone} change={v => edit(cat, r.key, 'timezone', v)} /></>}
          {cat === 'currency' && <Input label="Currency code" value={r.value} change={v => edit(cat, r.key, 'value', v)} />}
          {cat === 'amounts' && <><label>Amount type<select value={r.kind} onChange={e => edit(cat, r.key, 'kind', e.target.value)}>{kinds.map(k => <option value={k} key={k}>{amountNames[k]}</option>)}</select></label><Input label="Label" value={r.name} change={v => edit(cat, r.key, 'name', v)} /><div className="fields"><Input label="Amount (e.g. 120.00)" value={r.amount} change={v => edit(cat, r.key, 'amount', v)} /><Input label="Currency" value={r.currency} change={v => edit(cat, r.key, 'currency', v)} /></div></>}
          {cat.includes('conditions') && <label>Policy text<textarea value={r.value} rows={4} onChange={e => edit(cat, r.key, 'value', e.target.value)} /></label>}
          <label className="check"><input type="checkbox" checked={r.ambiguous} onChange={e => edit(cat, r.key, 'ambiguous', e.target.checked)} />Unresolved / conflicting term</label>
        </div>)}
        <button disabled={cat === 'included_items' && none} onClick={() => change(cat, [...rows[cat], row()])}>+ Add merchant condition</button>
        {cat === 'included_items' && <label className="check"><input type="checkbox" checked={none} disabled={!!rows[cat].length} onChange={e => { setNone(e.target.checked); setDirty(true) }} />Explicitly no included items</label>}
      </fieldset></div></section>)}
    <section className="panel"><h3>Save merchant booking</h3><Input label="Merchant name / provisional label" value={label} change={setLabel} /><label>Reason / proposal note<textarea value={reason} maxLength={2000} onChange={e => setReason(e.target.value)} /></label><Action className="primary" disabled={busy || conflict || !label.trim() || !reason.trim()} resolve={!busy && !conflict ? { label: !label.trim() ? 'Enter prototype editor label' : 'Add proposal reason', selector: !label.trim() ? '.merchant-editor > .panel:last-child input' : '.merchant-editor > .panel:last-child textarea' } : undefined} reason={busy ? 'Wait for the current request.' : conflict ? 'Refresh because the saved inputs changed.' : !label.trim() ? 'Enter a merchant / prototype editor label.' : 'Enter a reason for this merchant version.'} onClick={() => void save()}>Save as new merchant version</Action><p className="hint">{dirty ? 'Unsaved fields. Existing comparisons do not describe these edits.' : 'Form shows saved merchant values.'} Customer agreement and confirmation will not change.</p></section>
    </details><button className="primary return-to-comparison" onClick={() => setView('buyer')}>Review saved versions & compare →</button><p className="hint">Switching views retains unsaved fields. Save the proposal before comparing.</p></div>

  </section>
}
function Input({ label, value, change }: { label: string; value: string; change: (v: string) => void }) { return <label>{label}<input value={value} onChange={e => change(e.target.value)} /></label> }

function AmountValues({ terms, other, changed }: { terms: Claim[]; other: Claim[]; changed: boolean }) {
  return <table className="data-table comparison-amount-table"><caption className="sr-only">Stated amounts and currencies for this saved version</caption><colgroup><col /><col className="amount-col" /></colgroup><thead><tr><th scope="col">Charge</th><th scope="col" className="numeric">Amount / currency</th></tr></thead><tbody>{terms.length ? terms.map((term, index) => {
    const label = amountNames[term.kind || 'other'] || 'Other'
    const value = term.amount && term.currency ? `${term.currency} ${term.amount}` : [term.currency || 'Currency not specified', term.amount || 'Amount not specified'].join(' · ')
    const peer = other.find(t => t.kind === term.kind)
    const difference = changed && (!peer || peer.amount !== term.amount || peer.currency !== term.currency)
    return <tr key={index}><th scope="row">{label}{term.label && term.label !== label && <small className="original-wording">{term.label}</small>}{term.ambiguous && <small className="field-error">Needs clarification</small>}</th><td className="numeric">{difference ? <mark>{value}</mark> : value}</td></tr>
  }) : <tr><td colSpan={2}>Not specified</td></tr>}</tbody></table>
}

function Highlight({ text, other }: { text: string; other: string }) {
  const tokens = new Set(other.split(/(\s+)/))
  return <>{text.split(/(\s+)/).map((t, i) => !tokens.has(t) && t.trim() ? <mark key={i}>{t}</mark> : t)}</>
}
function ComparisonResults({ refreshToken, bookingId, blocked, comparison: c, dirty, onEdit }: { refreshToken: number; bookingId: string; blocked: boolean; comparison: Comparison; dirty: boolean; onEdit: () => void }) {
  const changes = c.results.filter(r => r.status !== 'matches')
  const matching = c.results.filter(r => r.status === 'matches')
  const amounts = c.results.find(r => r.category === 'amounts')
  const amount = (side: 'agreement_terms' | 'proposal_terms', kind: string) => { const terms = amounts?.[side].filter(t => t.kind === kind); return terms?.length === 1 ? terms[0] : undefined }
  const deposit = amount('agreement_terms', 'deposit'), merchantDeposit = amount('proposal_terms', 'deposit')
  const total = amount('agreement_terms', 'total_payable'), merchantTotal = amount('proposal_terms', 'total_payable')
  function result(r: Result) {
    const before = r.agreement_terms.map(describe).join('\n'), after = r.proposal_terms.map(describe).join('\n')
    const nonrefundable = r.category === 'deposit_conditions' && r.status === 'differs' && !c.stale && /refundable|refunded|returned/i.test(before) && !/non[- ]?refundable|not refundable/i.test(before) && /non[- ]?refundable|not refundable/i.test(after)
    return <article className={`difference-section result-${r.status}`} key={r.category}><div className="section-heading"><h3>{titles[r.category]}</h3><strong className="status-word"><span aria-hidden="true">{r.status === 'matches' ? '✓ ' : '! '}</span>{r.status === 'differs' ? 'Changed' : r.status === 'matches' ? 'Matches' : 'Needs clarification'}</strong></div>
      <p className="hint">{r.basis === 'gemini_policy' ? 'AI-assisted policy comparison · not a guarantee' : 'Saved-value comparison'} · {blockerText(r.reason)}</p>
      {nonrefundable && deposit && merchantDeposit && deposit.amount === merchantDeposit.amount && deposit.currency === merchantDeposit.currency && <div className="consequence"><strong>{deposit.currency} {deposit.amount} deposit affected</strong><p>Merchant wording changes refundable terms to non-refundable. {total && merchantTotal && total.amount === merchantTotal.amount && total.currency === merchantTotal.currency ? `Inclusive total stays ${total.currency} ${total.amount}; the deposit terms still changed.` : 'Review the component amounts alongside this policy.'} Exact refund consequences require reviewed cancellation rules.</p></div>}
      <div className="comparison-columns"><section><h4>Buyer-agreed · confirmed agreement</h4>{r.category === 'amounts' ? <AmountValues terms={r.agreement_terms} other={r.proposal_terms} changed={r.status === 'differs'} /> : <p className="term"><Highlight text={before || 'Not specified / explicitly none (see reason)'} other={after} /></p>}{r.agreement_quote && <blockquote className="citation">{r.agreement_quote}</blockquote>}{r.agreement_terms.some(t => t.citations?.length) && <EvidenceButton title={titles[r.category]} citations={r.agreement_terms.flatMap(t => t.citations ?? [])} />}</section><section><h4>Merchant-proposed · final booking</h4>{r.category === 'amounts' ? <AmountValues terms={r.proposal_terms} other={r.agreement_terms} changed={r.status === 'differs'} /> : <p className="term"><Highlight text={after || 'Not specified / explicitly none (see reason)'} other={before} /></p>}{r.proposal_quote && <blockquote className="citation">{r.proposal_quote}</blockquote>}</section></div>{r.status !== "matches" && <ClarificationPanel refreshToken={refreshToken} key={`${c.id}-${r.category}`} bookingId={bookingId} comparisonId={c.id} fingerprint={c.fingerprint} category={r.category} blocked={blocked || c.stale || dirty} />}</article>
  }
  return <section className="comparison-results"><div className="section-heading"><div><p className="eyebrow">AGREEMENT → FINAL BOOKING</p><h2>{c.stale ? 'Comparison needs refreshing' : changes.length === 1 ? `${changes[0].category === 'deposit_conditions' ? 'Deposit terms' : titles[changes[0].category]} ${changes[0].status === 'differs' ? 'changed' : 'need clarification'}` : changes.length ? `${changes.length} sections need attention` : c.results.length ? 'Saved terms match' : 'No comparison results'}</h2></div></div>
    {c.stale && <div className="notice attention"><strong>Out of date — do not rely on these results.</strong><p>{c.stale_reasons.map(blockerText).join(' ')} Refresh and explicitly compare the latest versions.</p></div>}
    {dirty && <p className="notice">Merchant edits are unsaved. This comparison describes saved versions only.</p>}
    {!c.stale && <p className="hint">Version-bound comparison, not approval or a guarantee. Refresh to check changes made elsewhere.</p>}
    {changes.map(result)}{!c.stale && changes.length > 0 && <section className="resolution-guide"><Status tone="blocked">Resolve before checkout</Status><h3>Choose which terms should stand.</h3><p>The merchant can save a corrected proposal, or you can make a reasoned correction to your agreement and confirm it again. Then explicitly compare the saved versions. A comparison never approves changed terms for you.</p><div className="resolution-actions"><button onClick={onEdit}>Edit merchant proposal →</button><Resolve label="Review buyer agreement" step="review" /></div></section>}{!!matching.length && <details className="matching-sections"><summary>{matching.length} matching section{matching.length === 1 ? '' : 's'} · view both versions</summary>{matching.map(result)}</details>}
    <TechnicalDetails data={{ comparison_id: c.id, comparison_fingerprint: c.fingerprint, agreement_id: c.agreement_id, agreement_fingerprint: c.agreement_fingerprint, proposal_id: c.proposal_id, proposal_fingerprint: c.proposal_fingerprint }} />
  </section>
}
