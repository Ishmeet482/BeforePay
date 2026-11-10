import SavedStateLoad from './SavedStateLoad'
import { BlockerContext, BlockerList } from './BlockerActions'
import PolicyConsistencyPanel from './PolicyConsistencyPanel'
import { WorkspaceReadContext } from './WorkspaceFrame'
import TechnicalDetails from './TechnicalDetails'
import { Action, EvidenceButton, humanTime, TaskIntro, Resolve, Status } from './product-ui'
import { useContext, useEffect, useRef, useState } from 'react'
import { friendlyError } from './conditions'
import { allPages, post, request, type Agreement, type Claim, type ReviewState } from './review-api'

type Target = { kind: 'agreement' | 'proposal'; id: string; fingerprint: string }
type Refund = { mode: 'amount' | 'percent'; value: string }
type Band = { rental_refund: Refund; deposit_refund: Refund; clause: string }
type Rules = { cutoff_hours: string; early_includes_boundary: boolean; early: Band; late: Band; deposit_clause: string; needs_clarification: boolean; clarification_note: string }
type Rule = { id: string; target: Target; source_version: number; version: number; fingerprint: string; rules: Rules; origin: string; blockers: string[]; approved_current: boolean; audit: { reason: string }; approval: unknown }
type Source = { target: Target; version: number; policies: { category: string; claim: Claim }[]; available: boolean }
type Proposal = { id: string; version: number; fingerprint: string; content: { deposit_conditions: Claim[]; cancellation_conditions: Claim[] } }
type Preview = { status: string; blockers: string[]; cancellation_at: string | null; previews: { target: Target; source_version: number; cancellation_at: string; pickup_at: string; refund: string; retained: string; currency: string; rental_refund: string; deposit_refund: string; applied_clause: string; deposit_clause: string; band: string; cutoff_at: string; early_includes_boundary: boolean }[] }
const blankBand = (): Band => ({ rental_refund: { mode: 'percent', value: '' }, deposit_refund: { mode: 'percent', value: '' }, clause: '' })
const blankRules = (): Rules => ({ cutoff_hours: '', early_includes_boundary: true, early: blankBand(), late: blankBand(), deposit_clause: '', needs_clarification: true, clarification_note: '' })
const text = (c: Claim) => typeof c.value === 'string' ? c.value : ''

export default function CancellationWorkspace({ bookingId, merchant = false }: { bookingId: string; merchant?: boolean }) {
  const { ruleRequest, snapshot, step: activeStep, workspace: activeWorkspace } = useContext(BlockerContext)
  const appliedRuleRequest = useRef(0)
  const markRead = useContext(WorkspaceReadContext)
  const base = `/bookings/${bookingId}`
  const [sources, setSources] = useState<Source[]>([])
  const [allRules, setAllRules] = useState<Rule[]>([])
  const [kind, setKind] = useState<'agreement' | 'proposal'>(merchant ? 'proposal' : 'agreement')
  const [saved, setSaved] = useState<Rule | null>(null)
  const [rules, setRules] = useState<Rules>(blankRules)
  const [dirty, setDirty] = useState(false)
  const [actor, setActor] = useState('')
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [complete, setComplete] = useState(false)
  const [resolved, setResolved] = useState(false)
  const [ack, setAck] = useState(false)
  const [local, setLocal] = useState('')
  const [zone, setZone] = useState('')
  const [both, setBoth] = useState(false)
  const [result, setResult] = useState<Preview | null>(null)
  const resultPanel = useRef<HTMLElement>(null)
  useEffect(() => {
    if (!result) return
    const frame = requestAnimationFrame(() => { const panel = resultPanel.current; if (panel?.getClientRects().length) { panel.focus({ preventScroll: true }); panel.scrollIntoView({ block: 'start' }) } })
    return () => cancelAnimationFrame(frame)
  }, [result])
  const [busy, setBusy] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  function latest(records: Rule[], s: Source | undefined) { return s ? records.filter(r => r.target.kind === s.target.kind && r.target.id === s.target.id).sort((a, b) => b.version - a.version)[0] ?? null : null }
  function show(records: Rule[], src: Source[], selectedKind: 'agreement' | 'proposal') {
    const r = latest(records, src.find(s => s.target.kind === selectedKind))
    setSaved(r); setRules(r ? structuredClone(r.rules) : blankRules()); setDirty(false)
    setComplete(false); setResolved(false); setAck(false); setResult(null)
  }
  async function load(signal?: AbortSignal, selectedKind = kind) {
    const [review, proposals, records] = await Promise.all([
      request<ReviewState>(`${base}/review`, { signal }), allPages<Proposal>(`${base}/merchant-bookings`, signal), allPages<Rule>(`${base}/cancellation/rules`, signal),
    ])
    const a = review.agreement_id ? await request<Agreement>(`${base}/agreements/${review.agreement_id}`, { signal }) : null
    if (signal?.aborted) return
    const src: Source[] = []
    if (a) src.push({ target: { kind: 'agreement', id: a.id, fingerprint: a.fingerprint }, version: a.version, available: review.confirmation_current, policies: ['deposit_conditions', 'cancellation_conditions'].flatMap(category => a.content.extraction[category as 'deposit_conditions' | 'cancellation_conditions'].map(e => ({ category, claim: e.claim }))) })
    const p = proposals[0]
    if (p) src.push({ target: { kind: 'proposal', id: p.id, fingerprint: p.fingerprint }, version: p.version, available: true, policies: ['deposit_conditions', 'cancellation_conditions'].flatMap(category => p.content[category as 'deposit_conditions' | 'cancellation_conditions'].map(claim => ({ category, claim }))) })
    setSources(src); setAllRules(records); show(records, src, selectedKind); setLoaded(true); markRead()
  }
  useEffect(() => { const c = new AbortController(); load(c.signal).catch(e => { if (!c.signal.aborted) setError(e.message) }).finally(() => { if (!c.signal.aborted) setBusy(false) }); return () => c.abort() }, [])
  useEffect(() => { const clear = () => setResult(null); window.addEventListener('contextkey:changed', clear); return () => window.removeEventListener('contextkey:changed', clear) }, [])
  useEffect(() => { if (!dirty) return; const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }; window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn) }, [dirty])
  useEffect(() => {
    if (activeStep !== 'cancellation' || !ruleRequest || ruleRequest.serial === appliedRuleRequest.current || ruleRequest.workspace !== activeWorkspace || ruleRequest.workspace !== (merchant ? 'merchant' : 'buyer') || busy) return
    appliedRuleRequest.current = ruleRequest.serial
    const savedSource = ruleRequest.kind === 'agreement' ? snapshot?.agreement : snapshot?.proposal
    // A pending/failed parent read is unknown, not evidence that this source
    // changed. Retain unsaved fields; explicit saves still recheck server versions.
    const needsSource = !!snapshot && savedSource?.id !== sources.find(s => s.target.kind === ruleRequest.kind)?.target.id
    const focusReview = () => requestAnimationFrame(() => { const panel = document.querySelector<HTMLElement>(`.workspace-host:not([hidden]) .rule-workbench`); if (panel instanceof HTMLDetailsElement) panel.open = true; panel?.scrollIntoView({ block: 'start' }); panel?.querySelector<HTMLElement>('summary')?.focus({ preventScroll: true }) })
    if (dirty && (ruleRequest.kind !== kind || needsSource) && !window.confirm('Switch or refresh rule source? Unsaved rule edits will be discarded. Cancel to keep them.')) return
    if (!dirty || ruleRequest.kind !== kind || needsSource) {
      setKind(ruleRequest.kind)
      void act(async () => { await load(undefined, ruleRequest.kind); focusReview() })
    } else focusReview() // Same saved source: retain unsaved fields.

  }, [ruleRequest, merchant, activeWorkspace, activeStep, busy, sources])
  const source = sources.find(s => s.target.kind === kind)
  const agreementRule = latest(allRules, sources.find(s => s.target.kind === 'agreement'))
  const proposalRule = latest(allRules, sources.find(s => s.target.kind === 'proposal'))
  const bothReady = agreementRule?.approved_current && proposalRule?.approved_current
  function change(next: Rules) { setRules(next); setDirty(true); setAck(false); setComplete(false); setResolved(false); setResult(null); setMessage('') }
  async function act(work: () => Promise<void>) { setBusy(true); setError(''); setMessage(''); setResult(null); try { await work() } catch (e) { setError(e instanceof Error ? e.message : 'Request failed. Refresh if source/rule versions changed.') } finally { setBusy(false) } }
  async function save(ai: boolean) {
    if (!source) return
    if (ai && dirty && !window.confirm('Replace unsaved fields with an unapproved AI rule proposal?')) return
    await act(async () => {
      const body = { target: source.target, customer_label: actor, expected_latest_rule_id: saved?.id ?? null, ...(ai ? {} : { reason, rules }) }
      await request<Rule>(`${base}/cancellation/rules${ai ? '/propose' : ''}`, { method: 'POST', body: JSON.stringify(body), signal: AbortSignal.timeout(75000) })
      await load(); setMessage(ai ? 'AI proposal saved, unapproved. Read all source clauses, correct rules and explicitly confirm before any calculation.' : 'New rule version saved, unapproved. Review and explicitly confirm it.')
    })
  }
  async function confirm() {
    if (!saved) return
    await act(async () => { await post(`${base}/cancellation/rules/${saved.id}/confirm`, { customer_label: actor, expected_fingerprint: saved.fingerprint, acknowledged: ack, complete_pre_pickup_policy: complete, no_unresolved_contradictions: resolved, review_note: note }); await load(); setMessage(merchant ? 'Merchant rules confirmed for this exact proposal and rule version. Buyer agreement and checkout approvals are unchanged.' : 'Rules confirmed for this exact source and rule version. You may now request a preview.') })
  }
  async function preview() {
    const ids = both ? [agreementRule!.id, proposalRule!.id] : [saved!.id]
    await act(async () => { const p = await post<Preview>(`${base}/cancellation/preview`, { rule_ids: ids, cancellation: { local_datetime: local || null, timezone: zone || null } }); setResult(p) })
  }
  function example() {
    if (dirty && !window.confirm('Replace unsaved fields with illustrative 48-hour rules?')) return
    const clauses = source?.policies.filter(p => p.category === 'cancellation_conditions') ?? []
    const deposits = source?.policies.filter(p => p.category === 'deposit_conditions') ?? []
    change({ cutoff_hours: '48', early_includes_boundary: true,
      early: { rental_refund: { mode: 'percent', value: '100' }, deposit_refund: { mode: 'percent', value: '100' }, clause: clauses.length === 2 ? text(clauses[0].claim) : '' },
      late: { rental_refund: { mode: 'percent', value: '0' }, deposit_refund: { mode: 'percent', value: '100' }, clause: clauses.length === 2 ? text(clauses[1].claim) : '' },
      deposit_clause: deposits.length === 1 ? text(deposits[0].claim) : '', needs_clarification: true,
      clarification_note: 'Illustrative rules only. Verify split, cutoff, boundary and every clause against this exact source; resolve contradictions before confirming.' })
  }
  if (!loaded) return <SavedStateLoad title="Cancellation" busy={busy} error={friendlyError(error)} refresh={() => void act(() => load())} />
  return <section className="workspace" aria-busy={busy}>
    <div className="toolbar"><div><h2>{merchant ? 'Merchant policy rules' : 'Cancellation calculator'}</h2><p>{merchant ? 'Prepare and review rules for the latest merchant proposal. Buyer agreement confirmation is separate.' : 'Preview a refund using reviewed rules. No cancellation or refund is performed.'}</p></div><button disabled={busy} onClick={() => { if (!dirty || window.confirm('Discard unsaved rules and refresh?')) void act(() => load()) }}>Refresh rules</button></div>

    {busy && <p role="status">Loading / saving / reviewing…</p>}{error && <div role="alert" className="notice error">{friendlyError(error)}{friendlyError(error) !== error && <TechnicalDetails label="Error details" data={{ error }} />}</div>}{message && <p role="status" className="notice success">{message}</p>}
    <TaskIntro owner={merchant ? "Merchant policy review" : "Cancellation preview"} title={merchant ? "Review the merchant-proposed policy" : "Choose a policy and cancellation instant"}>{merchant ? "Saving or approving merchant rules never confirms the buyer agreement or authorizes checkout. Reviewer labels remain provisional." : "Python calculates refunds from rules you explicitly reviewed and approved. This screen never cancels a booking or sends a refund."}</TaskIntro>
    <div className="policy-selection"><label>Policy source version<select value={kind} disabled={busy || merchant} onChange={e => { if (dirty && !window.confirm('Discard unsaved rule edits?')) return; const k = e.target.value as 'agreement' | 'proposal'; setKind(k); show(allRules, sources, k) }}>{!merchant && <option value="agreement">Buyer-agreed · confirmed agreement</option>}<option value="proposal">Merchant-proposed · latest booking</option></select></label><div className="policy-status"><strong>{source ? `${kind === 'agreement' ? 'Buyer agreement' : 'Merchant proposal'} version ${source.version}` : 'No saved source version'}</strong><Status tone={saved?.approved_current ? 'success' : 'attention'}>{saved?.approved_current ? 'Rules approved for this version' : 'Rule approval required before calculation'}</Status><small>{merchant ? "Fixed to the latest merchant proposal. Refresh saved inputs after a proposal revision." : "Changing selection clears the preview and selects rules for that source."}</small></div></div>
    {!merchant && <div className={`cancellation-flow ${result ? 'has-result' : ''}`}><section className="panel cancellation-start"><p className="eyebrow">FINANCIAL CONSEQUENCES</p><h2>What if you cancel?</h2><p>Choose the cancellation instant and explicit timezone.</p>{saved?.approved_current && <p className="approved-cutoff"><strong>Reviewed cutoff · {saved.rules.cutoff_hours} hours before pickup</strong><small>Exactly at cutoff belongs to the {saved.rules.early_includes_boundary ? 'earlier' : 'later'} cancellation band.</small></p>}<div className="fields"><Input type="datetime-local" label="Cancellation date & time" value={local} change={v => { setLocal(v); setResult(null) }} /><Input label="Explicit timezone (IANA or UTC offset)" value={zone} change={v => { setZone(v); setResult(null) }} /></div><label className="check"><input type="checkbox" checked={both} disabled={busy || (!bothReady && !both)} onChange={e => { setBoth(e.target.checked); setResult(null) }} />Side-by-side agreement and merchant previews (both need current approved complete rules)</label><Action className="primary" disabled={busy || dirty || !local || !zone || (both ? !bothReady : !saved?.approved_current)} resolve={!busy ? { label: dirty || (both ? !bothReady : !saved?.approved_current) ? 'Open rule review' : 'Enter cancellation instant', selector: dirty || (both ? !bothReady : !saved?.approved_current) ? '.rule-workbench > summary' : '.cancellation-start input' } : undefined} reason={busy ? 'Wait for the current request.' : dirty ? 'Save and explicitly confirm edited rules first.' : both && !bothReady ? 'Both agreement and proposal need current approved complete rules.' : !both && !saved?.approved_current ? 'Open rule review below and confirm complete rules for this source.' : 'Enter cancellation date, time and explicit timezone.'} onClick={() => void preview()}>Preview refund</Action></section>
    <section className="panel cancellation-result" ref={resultPanel} tabIndex={-1} aria-label="Cancellation preview" aria-live="polite"><p className="eyebrow">CALCULATION RESULT</p><h2>Cancellation preview</h2>{!result ? <div className="preview-empty"><h3>{busy ? 'Preparing reviewed context…' : error ? 'No new preview available' : 'Your refund breakdown will appear here'}</h3><p>{error ? 'Resolve the error above, then explicitly request a new preview. No refund has been calculated.' : 'Choose a cancellation instant and approved rules, then select Preview refund. No booking is cancelled and no money moves.'}</p></div> : <>{result.status !== 'ready' && <p className="notice attention"><strong>Needs clarification</strong> · No definite refund available.</p>}<BlockerList codes={result.blockers} scope={both ? {} : { kind, sourceVersion: source?.version, ruleVersion: saved?.version }} /><div className="comparison-columns">{result.previews.map(p => <article className="refund-result" key={p.target.kind}><h3>{p.target.kind === 'agreement' ? 'Buyer agreement' : 'Merchant proposal'} version {p.source_version}</h3><dl className="refund-ledger"><div><dt>Estimated refund</dt><dd>{p.currency} {p.refund}</dd></div><div><dt>Amount retained</dt><dd>{p.currency} {p.retained}</dd></div></dl><dl className="applied-cutoff"><div><dt>Applied cutoff</dt><dd>{humanTime(p.cutoff_at)}</dd></div><div><dt>Your cancellation instant</dt><dd>{humanTime(p.cancellation_at)}</dd></div></dl><p className="hint">Python-calculated preview from explicitly approved rules. No cancellation or refund action performed.</p><details className="help"><summary>Applied clauses & calculation details</summary><p>Cancellation: {humanTime(p.cancellation_at)}<br />Pickup: {humanTime(p.pickup_at)}<br />Cutoff: {humanTime(p.cutoff_at)} · boundary belongs to {p.early_includes_boundary ? 'earlier' : 'later'} band</p><p>Rental-fee refund {p.rental_refund} · Deposit refund {p.deposit_refund}</p><h4>Applied {p.band} clause</h4><blockquote className="citation">{p.applied_clause}</blockquote><h4>Reviewed deposit clause</h4><blockquote className="citation">{p.deposit_clause}</blockquote><TechnicalDetails data={{ source_id: p.target.id, fingerprint: p.target.fingerprint }} /></details></article>)}</div></>}</section></div>}
    <PolicyConsistencyPanel bookingId={bookingId} onState={state => {
      if (!state.blockers.length) return
      setResult(null)
      const update = (r: Rule): Rule => r.target.kind === 'proposal' && r.target.id === state.proposal_id ? { ...r, approved_current: false, blockers: [...new Set([...r.blockers, ...state.blockers])] } : r
      setAllRules(rows => rows.map(update)); setSaved(r => r ? update(r) : r)
    }} />

    {source ? <><div className="rule-area-heading"><p className="eyebrow">SEPARATE TASK · POLICY AUTHORING & HUMAN APPROVAL</p><h2>{merchant ? "Merchant policy preparation and approval" : "Rules behind the calculation"}</h2><p>Saving rules does not approve them. Review exact source clauses and confirm the saved rule version before calculating.</p></div><details className="rule-workbench" open={dirty || merchant}><summary>{saved?.approved_current ? 'Reviewed cancellation rules · view clauses, history or propose a new version' : 'Review rules before previewing · manual entry or Gemini proposal'}</summary><div className="version-meta"><span className="badge">{kind} version {source.version}</span><TechnicalDetails data={{ source_id: source.target.id, fingerprint: source.target.fingerprint }} /></div>{!source.available && <p className="notice error">Agreement confirmation is not current. Complete agreement review first.<Resolve label="Review buyer agreement" step="review" /></p>}
      <section className="panel"><h3>Read all deposit and cancellation clauses</h3><p>Resolve conflicting source clauses in agreement review or a new merchant proposal before confirming rules.</p>{source.policies.map((p, i) => <div className="citation" key={i}><strong>{p.category.replaceAll('_', ' ')}</strong><blockquote>{text(p.claim)}</blockquote>{p.claim.citations.length > 0 && <EvidenceButton title={p.category.replaceAll('_', ' ')} citations={p.claim.citations} />}{p.claim.citations.map((c, n) => <div key={n}><small>Original evidence{c.page_number ? ` · page ${c.page_number}` : ''}</small><blockquote>{c.quotation}</blockquote><TechnicalDetails label="Source details" data={{ source_id: c.source_id }} /></div>)}</div>)}</section>
      <section className="panel rule-authoring"><h3>Structured pre-pickup rules</h3><Input label="Your name / reviewer label" value={actor} change={setActor} /><p className="hint">Identity is provisional. AI only proposes unapproved rules; you review and confirm separately.</p><div className="sample-buttons"><button disabled={busy || !source.available} onClick={example}>Load 48-hour example · form only</button><Action className="ai-button" disabled={busy || !source.available || !actor.trim()} resolve={!busy ? !source.available ? { label: 'Review buyer agreement', step: 'review' } : { label: 'Enter reviewer name', selector: '.rule-workbench input' } : undefined} reason={busy ? 'Wait for the current request.' : !source.available ? 'Confirm the current agreement first.' : 'Enter your reviewer name above to request an AI proposal.'} onClick={() => void save(true)}>Propose rules with AI</Action></div><p className="hint">AI runs only when requested and uses your Gemini quota. All proposed rules need your review and confirmation.</p>
        <fieldset disabled={busy || !source.available}>
          <Input label="Cutoff hours (e.g. 48)" value={rules.cutoff_hours} change={v => change({ ...rules, cutoff_hours: v })} />
          <label>Exactly at cutoff belongs to<select value={rules.early_includes_boundary ? 'early' : 'late'} onChange={e => change({ ...rules, early_includes_boundary: e.target.value === 'early' })}><option value="early">Earlier band (at least cutoff hours)</option><option value="late">Later band (cutoff hours or less)</option></select></label>
          {(['early', 'late'] as const).map(b => <section className="claim-row" key={b}><h3>{b === 'early' ? 'Earlier cancellation' : 'Later cancellation, still before pickup'}</h3>{(['rental_refund', 'deposit_refund'] as const).map(c => <div className="fields" key={c}><label>{c === 'rental_refund' ? 'Rental-fee refund' : 'Deposit refund'} method<select value={rules[b][c].mode} onChange={e => change({ ...rules, [b]: { ...rules[b], [c]: { ...rules[b][c], mode: e.target.value as Refund['mode'] } } })}><option value="percent">Percent of this component</option><option value="amount">Explicit USD amount</option></select></label><Input label={rules[b][c].mode === 'percent' ? 'Refund percentage (100 = 100%)' : 'Refund amount (USD)'} value={rules[b][c].value} change={v => change({ ...rules, [b]: { ...rules[b], [c]: { ...rules[b][c], value: v } } })} /></div>)}<label>Exact supporting cancellation clause<textarea rows={3} value={rules[b].clause} onChange={e => change({ ...rules, [b]: { ...rules[b], clause: e.target.value } })} /></label></section>)}
          <label>Exact supporting deposit clause<textarea rows={3} value={rules.deposit_clause} onChange={e => change({ ...rules, deposit_clause: e.target.value })} /></label>
          <label className="check"><input type="checkbox" checked={rules.needs_clarification} onChange={e => change({ ...rules, needs_clarification: e.target.checked })} />Missing terms, contradictions or unsupported conditions remain unresolved</label>
          <label>Clarification notes<textarea value={rules.clarification_note} maxLength={2000} onChange={e => change({ ...rules, clarification_note: e.target.value })} /></label>
        </fieldset>
        <label>Reason for this rule version<textarea value={reason} maxLength={2000} onChange={e => setReason(e.target.value)} /></label><Action className="primary" disabled={busy || !source.available || !actor.trim() || !reason.trim()} resolve={!busy ? !source.available ? { label: 'Review buyer agreement', step: 'review' } : { label: !actor.trim() ? 'Enter reviewer name' : 'Add rule version reason', selector: !actor.trim() ? '.rule-authoring input' : '.rule-authoring > label:last-of-type textarea' } : undefined} reason={busy ? 'Wait for the current request.' : !source.available ? 'Confirm the current agreement first.' : !actor.trim() ? 'Enter your reviewer name.' : 'Enter a reason for this rule version.'} onClick={() => void save(false)}>Save rules for review</Action>
      </section>
      {saved && <section className="panel rule-confirmation"><h3>{kind === "proposal" ? "Review merchant policy rules" : "Review and confirm exact rules"}</h3><p>Policy-rule approval does not confirm the buyer agreement or approve checkout.</p><p>Rule version {saved.version} · {saved.origin === 'gemini' ? 'AI-proposed · requires human review' : 'Human-authored'} · {saved.approved_current ? 'Approved and current' : 'Not approved/current'}</p><TechnicalDetails data={{ rule_id: saved.id, fingerprint: saved.fingerprint, audit: saved.audit, approval: saved.approval, blockers: saved.blockers }} />{!!saved.blockers.length && <div className="notice error"><strong>Needs clarification</strong><BlockerList codes={saved.blockers} scope={{ kind, sourceVersion: saved.source_version, ruleVersion: saved.version }} /></div>}
        <label className="check"><input type="checkbox" checked={complete} disabled={dirty || busy} onChange={e => setComplete(e.target.checked)} />I checked every source clause; these rules completely cover pre-pickup cancellation and component refunds.</label>
        <label className="check"><input type="checkbox" checked={resolved} disabled={dirty || busy} onChange={e => setResolved(e.target.checked)} />No unresolved deposit/cancellation contradictions or unsupported exceptions remain.</label>
        <label className="check"><input type="checkbox" checked={ack} disabled={dirty || busy} onChange={e => setAck(e.target.checked)} />I approve rule version {saved.version} shown here for {kind} version {saved.source_version}.</label>
        <label>Review note<textarea maxLength={2000} value={note} onChange={e => setNote(e.target.value)} /></label><Action className="primary" disabled={busy || dirty || !source.available || !actor.trim() || !note.trim() || !complete || !resolved || !ack || saved.blockers.length > 0 || saved.approved_current} resolve={!busy && !saved.approved_current ? !source.available ? { label: 'Review buyer agreement', step: 'review' } : { label: dirty || saved.blockers.length ? 'Review rule fields' : !actor.trim() ? 'Enter reviewer name' : !note.trim() ? 'Add review note' : 'Review approval attestations', selector: dirty || saved.blockers.length ? '.rule-authoring' : !actor.trim() ? '.rule-authoring input' : !note.trim() ? '.rule-confirmation textarea' : '.rule-confirmation .check input' } : undefined} reason={saved.approved_current ? 'This rule version is already approved and current.' : busy ? 'Wait for the current request.' : dirty ? 'Save rule edits as a new version first.' : !source.available ? 'Renew agreement confirmation first.' : saved.blockers.length ? 'Resolve the listed rule blockers before confirmation.' : !actor.trim() ? 'Enter your reviewer name.' : !note.trim() ? 'Add a review note.' : 'Check all three review and exact-version approval attestations.'} onClick={() => void confirm()}>{merchant ? "Confirm reviewed merchant rules" : "Confirm reviewed rules"}</Action>
      </section>}
      {!!allRules.filter(r => !merchant || r.target.kind === "proposal").length && <details className="rule-history"><summary>Saved rule history · {allRules.filter(r => !merchant || r.target.kind === "proposal").length} versions</summary>{allRules.filter(r => !merchant || r.target.kind === "proposal").map(r => <article className="panel" key={r.id}><h4>{r.target.kind} source version {r.source_version} · rule version {r.version}</h4><p className="hint">{r.origin === 'gemini' ? 'AI-proposed' : 'Human-authored'} · {r.approved_current ? 'Approved and current' : 'Not approved/current'}</p><p>Cutoff {r.rules.cutoff_hours} hours; exact boundary belongs to {r.rules.early_includes_boundary ? 'earlier' : 'later'} band.</p><blockquote>{r.rules.early.clause}</blockquote><blockquote>{r.rules.late.clause}</blockquote><blockquote>{r.rules.deposit_clause}</blockquote><TechnicalDetails label="Rule fields, provenance and approval" data={{ ...r }} /></article>)}</details>}
    </details></> : <p className="notice">{error ? 'Saved source version status unavailable. Refresh before continuing.' : <>No {kind} version available. Confirm an agreement or explicitly save a merchant proposal in the other tabs.</>}<Resolve label={kind === 'agreement' ? 'Review buyer agreement' : 'Open merchant proposal'} step={kind === 'agreement' ? 'review' : 'comparison'} /></p>}

    <details className="help"><summary>How this preview works</summary><p>Pre-pickup only: one cutoff and separate rental-fee/deposit refunds in USD cents. The stated rental fee plus deposit must equal total payable. Unsupported or conflicting policies need clarification. This preview does not cancel a booking or move money.</p></details>
  </section>
}
function Input({ label, value, change, type = 'text' }: { label: string; value: string; change: (v: string) => void; type?: string }) { return <label>{label}<input type={type} value={value} onChange={e => change(e.target.value)} /></label> }
