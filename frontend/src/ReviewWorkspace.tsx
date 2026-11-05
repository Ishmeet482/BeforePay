import CategorySummary from './CategorySummary'
import { WorkspaceReadContext } from './WorkspaceFrame'
import TechnicalDetails from './TechnicalDetails'
import { Action, EvidenceButton, humanTime, TaskIntro, Resolve, Status } from './product-ui'
import { useContext, useEffect, useRef, useState } from 'react'
import { allPages, ApiError, categories, kinds, post, request, type Agreement, type Category, type Draft, type ReviewState, type Source } from './review-api'
import { blockerText, friendlyError, claim, relevant, row, rowsChanged, titles, type Row } from './conditions'

type Rows = Record<Category, Row[]>
const emptyRows = () => Object.fromEntries(categories.map(c => [c, [] as Row[]])) as Rows

export default function ReviewWorkspace({ bookingId }: { bookingId: string }) {
  const markRead = useContext(WorkspaceReadContext)
  const base = `/bookings/${bookingId}`
  const [versions, setVersions] = useState<Agreement[]>([])
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [agreement, setAgreement] = useState<Agreement | null>(null)
  const [review, setReview] = useState<ReviewState | null>(null)
  const [sources, setSources] = useState<Source[]>([])
  const [rows, setRows] = useState<Rows>(emptyRows)
  const [reasons, setReasons] = useState<Partial<Record<Category, string>>>({})
  const [reviewReason, setReviewReason] = useState('')
  const [actor, setActor] = useState('')
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [noItems, setNoItems] = useState(false)
  const [ack, setAck] = useState(false)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [stale, setStale] = useState(false)
  const mounted = useRef(true)
  const generation = useRef(0)

  function show(a: Agreement | null) {
    setAgreement(a)
    setRows(a ? Object.fromEntries(categories.map(c => [c, a.content.extraction[c].map(row)])) as Rows : emptyRows())
    setReasons({}); setReviewReason(''); setChecked(new Set()); setAck(false)
    setNoItems(a?.content.explicit_none_categories.includes('included_items') ?? false)
  }
  async function load(signal?: AbortSignal, preferredId?: string) {
    const serial = ++generation.current
    const [v, d, state, summaries] = await Promise.all([
      allPages<Agreement>(`${base}/agreements`, signal), allPages<Draft>(`${base}/drafts`, signal),
      request<ReviewState>(`${base}/review`, { signal }), allPages<{ id: string }>(`${base}/sources`, signal),
    ])
    const evidence = await Promise.all(summaries.map(s => request<Source>(`${base}/sources/${s.id}`, { signal })))
    if (!mounted.current || signal?.aborted || serial !== generation.current) return
    setVersions(v); setDrafts(d); setReview(state); setSources(evidence)
    show(v.find(a => a.id === (preferredId ?? state.agreement_id)) ?? v[0] ?? null)
    setStale(false); markRead()
  }
  useEffect(() => {
    mounted.current = true
    const controller = new AbortController()
    load(controller.signal).catch(e => { if (!controller.signal.aborted) setError(`Could not load review. ${e.message}`) })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => { mounted.current = false; controller.abort() }
    // Workspace is keyed by booking; each mount owns its requests and edit state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const changed = new Set(categories.filter(category => agreement && (
    rowsChanged(category, rows[category], agreement.content.extraction[category]) ||
    (category === 'included_items' && noItems !== agreement.content.explicit_none_categories.includes(category))
  )))
  const dirty = changed.size > 0
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
  const latest = agreement?.id === review?.agreement_id && agreement?.fingerprint === review?.fingerprint
  const oldDraft = !!review?.blockers.includes('newer_ai_draft_requires_review')
  const editable = latest && !stale && !oldDraft && !busy
  const allReviewed = sources.length > 0 && sources.every(s => checked.has(s.id))
  const canSave = editable && allReviewed && actor.trim() && reviewReason.trim() &&
    [...changed].every(c => reasons[c]?.trim())
  const canConfirm = editable && !dirty && allReviewed && ack && actor.trim() &&
    review?.blockers.length === 0 && !review.confirmation_current

  function change(category: Category, next: Row[]) {
    setRows(r => ({ ...r, [category]: next }))
    setAck(false); setSuccess('')
  }
  async function act(action: () => Promise<void>) {
    setBusy(true); setError(''); setSuccess('')
    try { await action() } catch (e) {
      if (!mounted.current) return
      setError(e instanceof Error ? e.message : 'Request failed.')
      if (e instanceof ApiError && e.status === 409) { setStale(true); setAck(false) }
    } finally { if (mounted.current) setBusy(false) }
  }
  async function save() {
    if (!canSave || !agreement) return
    await act(async () => {
      const changes = [...changed].map(category => ({ category, reason: reasons[category],
        items: rows[category].map(r => claim(category, r)), ...(category === 'included_items' ? { explicit_none: noItems } : {}) }))
      const next = await post<Agreement>(`${base}/agreements/${agreement.id}/revisions`, {
        expected_fingerprint: agreement.fingerprint, customer_label: actor,
        review_reason: reviewReason, reviewed_source_ids: sources.filter(s => checked.has(s.id)).map(s => s.id), changes,
      })
      await load(undefined, next.id)
      if (mounted.current) setSuccess(`Version ${next.version} saved. Review this version, acknowledge sources again, then explicitly confirm.`)
    })
  }
  async function confirm() {
    if (!canConfirm || !agreement) return
    await act(async () => {
      await post(`${base}/agreements/${agreement.id}/confirmations`, {
        expected_fingerprint: agreement.fingerprint, customer_label: actor, acknowledged: true,
      })
      await load(undefined, agreement.id)
      if (mounted.current) setSuccess('This exact agreement version is confirmed.')
    })
  }
  function refresh() {
    if (dirty && !window.confirm('Discard unsaved edits and load the latest version?')) return
    void act(() => load())
  }
  const blocks = review?.blockers ?? []

  function categorySection(category: Category) {
    return <section className="panel condition" key={category} aria-labelledby={`title-${category}`}>
        <div className="section-heading"><h3 id={`title-${category}`}>{titles[category]}</h3><span className="badge">{changed.has(category) ? 'Unsaved correction' : 'Saved'}</span></div>
        {blocks.filter(b => relevant(category, b)).map(b => <p className="field-error" key={b}>{blockerText(b)}</p>)}
        <CategorySummary category={category} rows={rows[category]} noItems={noItems} />
        <details className="section-editor"><summary>{editable ? `Edit ${titles[category].toLowerCase()}` : 'View saved fields'}</summary>
        {category === 'amounts' && <p className="hint">Total payable includes the rental fee and deposit; it is not an extra charge. Enter amounts such as 120.00.</p>}
        {category === 'cancellation_conditions' && <details className="help"><summary>Combining policy clauses</summary><p>Complementary clauses can stay separate. If you combine them, keep every clause, remove only the duplicated rows and explain the change.</p></details>}
        {!rows[category].length && <p className="hint">{category === 'included_items' && noItems ? 'Explicitly no included items.' : 'Unknown — no conditions recorded.'}</p>}
        {rows[category].map((r, index) => <div className="claim-row" key={r.key}>
          <div className="claim-heading"><small>{changed.has(category) ? 'Unsaved customer correction · original evidence below' : r.original?.origin === 'customer_entered' ? 'Customer-entered correction' : 'Source-supported condition'}</small>
            <button type="button" className="text-button" disabled={!editable} onClick={() => change(category, rows[category].filter(x => x.key !== r.key))} aria-label={`Remove ${titles[category]} row ${index + 1}`}>Remove</button></div>
          <fieldset disabled={!editable} aria-label={`${titles[category]} row ${index + 1}`}>
            {(category === 'equipment' || category === 'included_items') && <div className="fields"><Field label="Item" value={r.name} onChange={name => change(category, rows[category].map(x => x.key === r.key ? { ...x, name } : x))} /><Field label="Quantity" inputMode="numeric" value={r.quantity} onChange={quantity => change(category, rows[category].map(x => x.key === r.key ? { ...x, quantity } : x))} /></div>}
            {(category === 'pickup' || category === 'return_time') && <div className="fields"><Field label="Local date & time (ISO)" placeholder="2026-11-01T09:00:00" value={r.value} onChange={value => change(category, rows[category].map(x => x.key === r.key ? { ...x, value } : x))} /><Field label="Explicit timezone" placeholder="UTC / Asia/Kolkata / +05:30" value={r.timezone} onChange={timezone => change(category, rows[category].map(x => x.key === r.key ? { ...x, timezone } : x))} /></div>}
            {category === 'currency' && <Field label="Currency code" placeholder="USD" value={r.value} onChange={value => change(category, rows[category].map(x => x.key === r.key ? { ...x, value } : x))} />}
            {category === 'amounts' && <><div className="fields"><label>Amount type<select value={r.kind} onChange={e => change(category, rows[category].map(x => x.key === r.key ? { ...x, kind: e.target.value } : x))}>{kinds.map(k => <option value={k} key={k}>{({ rental_total: 'Rental fee', total_payable: 'Total payable (inclusive)', deposit: 'Deposit', tax: 'Tax', delivery: 'Delivery', other: 'Other' })[k]}</option>)}</select></label><Field label="Label" value={r.name} onChange={name => change(category, rows[category].map(x => x.key === r.key ? { ...x, name } : x))} /></div><div className="fields"><Field label="Amount" inputMode="decimal" value={r.amount} onChange={amount => change(category, rows[category].map(x => x.key === r.key ? { ...x, amount } : x))} /><Field label="Currency" value={r.currency} onChange={currency => change(category, rows[category].map(x => x.key === r.key ? { ...x, currency } : x))} /></div></>}
            {(category === 'deposit_conditions' || category === 'cancellation_conditions') && <label>Policy clause<textarea rows={4} value={r.value} onChange={e => change(category, rows[category].map(x => x.key === r.key ? { ...x, value: e.target.value } : x))} /></label>}
            <label className="check"><input type="checkbox" checked={r.ambiguous} onChange={e => change(category, rows[category].map(x => x.key === r.key ? { ...x, ambiguous: e.target.checked } : x))} />Unresolved / conflicting condition</label>
          </fieldset>
          {r.original?.reason && <p className="hint">Saved correction reason: {r.original.reason}</p>}
          {r.original?.claim.citations.map((c, i) => <div className="citation" key={i}><EvidenceButton title={titles[category]} citations={[c]} /><blockquote>{c.quotation}</blockquote></div>)}
        </div>)}
        <button disabled={!editable || (category === 'included_items' && noItems)} onClick={() => change(category, [...rows[category], row()])}>+ Add {category.includes('conditions') ? 'clause' : 'condition'}</button>
        {category === 'included_items' && <label className="check"><input type="checkbox" disabled={!editable || rows.included_items.length > 0} checked={noItems} onChange={e => { setNoItems(e.target.checked); change(category, rows[category]) }} />Explicitly no included items (remove rows first)</label>}
        {changed.has(category) && <label className="reason">Reason for {titles[category].toLowerCase()} correction<textarea required maxLength={2000} rows={2} value={reasons[category] ?? ''} onChange={e => setReasons(s => ({ ...s, [category]: e.target.value }))} disabled={!editable} /></label>}
        </details>
      </section>
  }
  return <div className="workspace" aria-busy={busy}>
    <div className="toolbar"><div><h2>Agreement review</h2><p>Saved versions only. Your edits create a new version.</p></div>
      <button onClick={refresh} disabled={busy}>Refresh latest</button></div>
    {busy && <p role="status">Loading / saving…</p>}
    {error && <div role="alert" className="notice error">{friendlyError(error)}{friendlyError(error) !== error && <TechnicalDetails label="Error details" data={{ error }} />}{stale && <p>Server rejected this review. Unsaved edits remain visible. Refresh latest before continuing.</p>}</div>}
    {success && <p role="status" className="notice success">{success}</p>}
    <TaskIntro owner={review?.confirmation_current && latest ? 'Buyer-confirmed agreement' : 'Unconfirmed buyer review'} title="Review evidence. Save corrections. Confirm separately.">This is your quotation baseline. Merchant proposals stay separate; confirmation applies only to this exact saved version.</TaskIntro>
    {(!agreement || oldDraft) && <label className="identity">Your name / reviewer label<input value={actor} maxLength={100} onChange={e => setActor(e.target.value)} disabled={busy} autoComplete="name" /><small>Recorded with your review. Identity is not verified in this prototype.</small></label>}
    {!!versions.length && <details className="agreement-history"><summary>Saved agreement versions · review history</summary><label>Agreement version<select value={agreement?.id ?? ''} disabled={busy} onChange={e => {
      if (dirty && !window.confirm('Discard unsaved edits and open this saved version?')) return
      show(versions.find(v => v.id === e.target.value) ?? null); setError(''); setSuccess('')
    }}>{versions.map(v => <option key={v.id} value={v.id}>Version {v.version} · {humanTime(v.created_at)}{v.id === review?.agreement_id ? ' · latest' : ' · history'}</option>)}</select></label></details>}
    {agreement && <div className="version-meta"><Status tone={review?.confirmation_current && latest ? 'success' : latest ? 'attention' : 'neutral'}>{review?.confirmation_current && latest ? 'Confirmed' : latest ? 'Review required' : 'Historical · read only'}</Status>
      <span>Version {agreement.version} · {humanTime(agreement.created_at)}</span><TechnicalDetails data={{ agreement_id: agreement.id, draft_id: agreement.draft_id, fingerprint: agreement.fingerprint, audit: agreement.audit }} /></div>}
    {!latest && agreement && <p className="notice">Historical version. Open latest to save corrections or confirm.</p>}
    {(!agreement || oldDraft) && <section className="panel"><h3>Open a saved AI draft</h3><p>No extraction will run. Opening a draft creates an unconfirmed review version.</p>
      {drafts.length ? <button disabled={busy || !actor.trim()} onClick={() => {
        if (dirty && !window.confirm('Discard unsaved changes and open the newer draft?')) return
        void act(async () => { const a = await post<Agreement>(`${base}/agreements/from-draft`, { draft_id: drafts[0].id, customer_label: actor }); await load(undefined, a.id); setSuccess('Saved draft opened for review. Nothing is confirmed.') })
      }}>Open latest saved draft · {drafts[0].version}</button> : <p>No saved draft available. Add evidence and explicitly generate one in Sources &amp; draft.<Resolve label="Open source inbox" step="sources" /></p>}</section>}
    {drafts.length > 0 && (!agreement || oldDraft) && !actor.trim() && <p className="action-explanation">Enter your reviewer name to open a saved draft.</p>}
    {!!blocks.length && <div className="notice attention" aria-label="Review blockers"><strong>{blocks.length} item(s) need review</strong><p>Resolve the highlighted fields and any issues below before confirming.</p><ul>{blocks.filter(b => !categories.some(c => relevant(c, b))).map(b => <li key={b}>{blockerText(b)}</li>)}</ul></div>}
    <div className="review-grid"><div className="conditions">
      {agreement && <>
        <section className="agreement-group" data-agreement-group="equipment"><h2>Equipment &amp; included items</h2><div className="items-grid">{categorySection('equipment')}{categorySection('included_items')}</div></section>
        <section className="agreement-group" data-agreement-group="schedule"><h2>Rental schedule</h2><div className="schedule-grid">{categorySection('pickup')}{categorySection('return_time')}</div></section>
        <section className="agreement-group" data-agreement-group="amounts"><h2>Amount breakdown</h2>{categorySection('amounts')}{categorySection('currency')}<p className="hint">Inclusive total is the stated total, not an additional charge. No amounts are calculated here.</p></section>
        <section className="agreement-group" data-agreement-group="policies"><h2>Policy clauses</h2>{categorySection('deposit_conditions')}{categorySection('cancellation_conditions')}</section>
      </>}
    </div><aside className="evidence"><h2>Source acknowledgements</h2><p>Open each original source beside your terms, then acknowledge your review.</p>
      {sources.map((s, index) => <section className="panel source" id={`source-${s.id}`} key={s.id}><h3>{s.filename || `${s.source_type} ${index + 1}`}</h3><small>{s.source_type} · {s.medium === 'pdf' ? 'PDF' : 'Pasted text'}</small><TechnicalDetails label="Source details" data={{ source_id: s.id, medium: s.medium }} />
        <EvidenceButton title={s.filename || `Source ${index + 1}`} sourceId={s.id} citations={[]} />
        <label className="check"><input type="checkbox" checked={checked.has(s.id)} disabled={busy || !latest || stale} onChange={e => { setChecked(old => { const n = new Set(old); if (e.target.checked) n.add(s.id); else n.delete(s.id); return n }); setAck(false) }} />I read and reviewed this source</label></section>)}
      {!sources.length && !busy && <p>No evidence available.</p>}
    </aside></div>
    {agreement && <details className="review-actions" open={!(review?.confirmation_current && latest) || dirty}><summary>{review?.confirmation_current && latest ? `Agreement version ${agreement.version} confirmed · review history or make corrections` : 'Save review & confirm agreement'}</summary>{!oldDraft && <div className="review-identity"><label className="identity">Your name / reviewer label<input value={actor} maxLength={100} onChange={e => setActor(e.target.value)} disabled={busy} autoComplete="name" /><small>Recorded with your review. Identity is not verified in this prototype.</small></label></div>}<section className="panel save-panel" id="review-save"><p className="eyebrow">STEP 1 · SAVE A REVIEW RECORD</p><h2>Save your review</h2><p>Save your review with a reason, even if no terms changed. Changed sections need their own reasons. Confirmation is a separate step.</p>
      <label>Overall review reason<textarea maxLength={2000} rows={2} value={reviewReason} disabled={!editable} onChange={e => setReviewReason(e.target.value)} placeholder="Explain the corrections or why the current terms still apply to all reviewed sources." /></label>
      <p className="hint">{checked.size} / {sources.length} sources reviewed · {changed.size} changed section(s).</p>
      <Action className="primary" disabled={!canSave} resolve={!busy && editable ? { label: !actor.trim() ? 'Enter reviewer name' : !allReviewed ? 'Review sources' : !reviewReason.trim() ? 'Add review reason' : 'Review section corrections', selector: !actor.trim() ? '.identity input' : !allReviewed ? '.evidence' : !reviewReason.trim() ? '.save-panel textarea' : '.condition .reason textarea' } : !busy ? { label: 'Open latest saved version', selector: '.agreement-history select' } : undefined} reason={busy ? 'Wait for the current request.' : !editable ? 'Open the latest agreement and refresh stale inputs before saving.' : !actor.trim() ? 'Enter your reviewer name above.' : !allReviewed ? 'Read and acknowledge every source first.' : !reviewReason.trim() ? 'Enter an overall review reason.' : 'Add a correction reason for each changed section.'} onClick={() => void save()}>Save review</Action></section>
      <section className="panel confirm-panel"><p className="eyebrow">STEP 2 · EXPLICIT HUMAN APPROVAL</p><h2>Confirm this exact version</h2><p>Version {agreement.version} · confirmation requires complete terms and no unresolved blockers. Save edits first.</p>
        <label className="check"><input type="checkbox" disabled={!editable || dirty || !allReviewed || !!blocks.length} checked={ack} onChange={e => setAck(e.target.checked)} />I reviewed all conditions and sources and explicitly agree to version {agreement.version} shown above.</label>
        <Action className="primary" disabled={!canConfirm} resolve={!busy && editable && !review?.confirmation_current ? { label: dirty ? 'Save corrections' : !actor.trim() ? 'Enter reviewer name' : !allReviewed ? 'Review sources' : blocks.length ? 'Review incomplete terms' : 'Review acknowledgement', selector: dirty ? '.save-panel' : !actor.trim() ? '.identity input' : !allReviewed ? '.evidence' : blocks.length ? '.conditions' : '.confirm-panel .check input' } : undefined} reason={review?.confirmation_current && latest ? 'This exact version is already confirmed.' : busy ? 'Wait for the current request.' : !editable ? 'Refresh and open the latest saved version.' : dirty ? 'Save corrections first; confirmation is a separate action.' : !actor.trim() ? 'Enter your reviewer name above.' : !allReviewed ? 'Acknowledge every source first.' : blocks.length ? 'Resolve the listed incomplete or conflicting terms.' : 'Tick the exact-version agreement acknowledgement.'} onClick={() => void confirm()}>Confirm version {agreement.version}</Action>
        {review?.confirmation_current && latest && <p className="success">Confirmed by {review.confirmation?.customer_label} · {review.confirmation?.created_at && humanTime(review.confirmation.created_at)}</p>}
      </section>
</details>}
  </div>
}

function Field({ label, value, onChange, placeholder, inputMode }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; inputMode?: 'numeric' | 'decimal' }) {
  return <label>{label}<input value={value} placeholder={placeholder} inputMode={inputMode} onChange={e => onChange(e.target.value)} /></label>
}

