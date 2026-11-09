import { BlockerContext, BlockerList, BlockerNext } from './BlockerActions'
import type { Destination } from './blocker-actions'
import { useEffect, useRef, useState } from 'react'
import { allPages, post, type Booking } from './review-api'
import WorkspaceFrame from './WorkspaceFrame'
import EntryPage from './EntryPage'
import ReviewWorkspace from './ReviewWorkspace'
import ComparisonWorkspace from './ComparisonWorkspace'
import CancellationWorkspace from './CancellationWorkspace'
import CheckoutWorkspace from './CheckoutWorkspace'
import EvidenceWorkspace, { intakeError } from './EvidenceWorkspace'
import { loadSnapshot, nextStep, snapshotClaims, stageState, type Snapshot, type Step } from './booking-state'
import { Action, describeClaim, EvidenceProvider, humanTime, JourneyContext, money, Status } from './product-ui'
import { BuyerReference, MerchantOverview, MerchantPayment } from './MerchantWorkspace'
import { parseWorkspaceRoute, workspaceRoute, workspaceNext, type Workspace } from './workspace-state'
import MerchantClarifications from './MerchantClarifications'
import DemoLogin from './DemoLogin'
import DemoIdentity from './DemoIdentity'
import Brand from './Brand'
import { rentalCategories, type RentalCategory } from './rental-categories'
import { readDemoRole, retainDemoRole } from './demo-session'
import { enterServerSession, leaveServerSession } from './server-session'

const steps: { id: Step; label: string; detail: string }[] = [
  { id: 'overview', label: 'Overview', detail: 'Your booking at a glance' },
  { id: 'sources', label: 'Sources & draft', detail: 'Quotation, messages and PDFs' },
  { id: 'review', label: 'Agreement', detail: 'Review and confirm terms' },
  { id: 'comparison', label: 'Compare booking', detail: 'Changes in the final booking' },
  { id: 'cancellation', label: 'Cancellation', detail: 'Review rules and preview refund' },
  { id: 'checkout', label: 'Checkout & receipt', detail: 'Sandbox payment' },
]
function useSnapshot(id: string, epoch: number, active = true) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!active) return
    const c = new AbortController(); setError('')
    loadSnapshot(id, c.signal).then(s => { if (!c.signal.aborted) setSnapshot(s) }).catch(e => { if (!c.signal.aborted) setError(intakeError(e)) })
    return () => c.abort()
  }, [id, epoch, active])
  return { snapshot, error }
}
function BookingRow({ booking, onOpen, epoch, workspace, active }: { booking: Booking; onOpen: (step: Step) => void; epoch: number; workspace: Workspace; active: boolean }) {
  const { snapshot, error } = useSnapshot(booking.id, epoch, active)
  const claims = snapshotClaims(snapshot ?? undefined)
  const total = claims?.amounts?.filter(c => c.kind === 'total_payable')
  const next = snapshot && !error ? workspaceNext(snapshot, workspace) : null
  const label = error ? 'Review booking status' : next?.label || 'Open booking'
  return <tr className="booking-row">
    <th scope="row" className="booking-name" data-label="Booking / equipment"><h2>{booking.title}</h2><p>{claims?.equipment?.map(describeClaim).join(' · ') || 'Equipment not specified'}</p></th>
    {workspace === 'merchant' ? <><td data-label="Buyer agreement"><strong>{error ? 'Status unavailable' : snapshot ? snapshot.review.confirmation_current ? `Confirmed version ${snapshot.agreement?.version}` : 'Buyer review needed' : 'Checking…'}</strong><small>Read-only reference</small></td><td data-label="Merchant proposal / rules"><strong>{error ? 'Status unavailable' : snapshot?.proposal ? `Proposal version ${snapshot.proposal.version}` : snapshot ? 'Merchant proposal needed' : 'Checking…'}</strong>{snapshot && !error && <small>{snapshot.rules.some(r => r.target.kind === 'proposal' && r.target.id === snapshot.proposal?.id && r.approved_current) ? 'Merchant rules reviewed' : 'Merchant policy review needed'}</small>}</td></> : <>    <td data-label="Rental schedule"><p>Pickup {claims?.pickup?.length === 1 && !claims.pickup[0].ambiguous ? humanTime(claims.pickup[0].value) : 'not specified'}</p><small>Return {claims?.return_time?.length === 1 && !claims.return_time[0].ambiguous ? humanTime(claims.return_time[0].value) : 'not specified'}</small></td>
    <td className="numeric" data-label="Inclusive total"><strong>{snapshot?.receipt ? money(snapshot.receipt.amount, snapshot.receipt.currency) : total?.length === 1 && !total[0].ambiguous ? money(total[0].amount, total[0].currency) : 'Not specified'}</strong>{snapshot && !snapshot.review.confirmation_current && !snapshot.receipt && <small>Unconfirmed terms</small>}</td>
</>}
    <td data-label="Current status"><span className="state-label"><Status tone={error ? 'blocked' : next?.tone || 'neutral'}>{error ? 'Status unavailable' : next?.status || 'Checking status…'}</Status></span>{error && <small>{error}</small>}</td>
    <td className="table-actions" data-label="Next action"><button className="row-action" title={label} onClick={() => onOpen(next?.step || 'overview')} aria-label={`${label}: ${booking.title}`}><span>{label}</span><span aria-hidden="true">→</span></button></td>
  </tr>
}
export default function App() {
  useEffect(() => {
    const header = document.querySelector('.app-header')
    if (!header) return
    const observer = new ResizeObserver(() => document.documentElement.style.setProperty('--app-header-height', `${header.getBoundingClientRect().height}px`))
    observer.observe(header); return () => observer.disconnect()
  }, [])
  const [identity, setIdentity] = useState<Workspace | null>(readDemoRole)
  const focusAfterSignOut = useRef(false)
  useEffect(() => {
    if (identity || !focusAfterSignOut.current) return
    focusAfterSignOut.current = false
    const frame = requestAnimationFrame(() => document.querySelector<HTMLButtonElement>('.login-entry')?.focus())
    return () => cancelAnimationFrame(frame)
  }, [identity])
  const identityRef = useRef(identity); identityRef.current = identity
  const [login, setLogin] = useState<{ role: Workspace; hash: string; step?: Step; selector?: string; buyerOnly?: boolean } | null>(null)
  const [sessionNotice, setSessionNotice] = useState('')
  const [bookings, setBookings] = useState<Booking[]>([])
  const [rawRoute, setRoute] = useState(() => window.location.hash.slice(1) || 'home')
  const { route, workspace } = parseWorkspaceRoute(rawRoute)
  const [selected, setSelected] = useState(() => { const id = parseWorkspaceRoute(window.location.hash.slice(1)).id; return id === 'new' ? '' : id || '' })
  const selectedRef = useRef(selected)
  const lastRoute = useRef(identity && workspace === identity && !route.endsWith('/new') ? rawRoute : identity ? workspaceRoute(identity) : 'home')
  const [entry, setEntry] = useState<{ step: Step; serial: number; selector?: string }>({ step: 'overview', serial: 0 })
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [title, setTitle] = useState('')
  const [rentalCategory, setRentalCategory] = useState<RentalCategory | ''>('')
  const [creating, setCreating] = useState(false)
  const [creationNeedsRefresh, setCreationNeedsRefresh] = useState(false)
  const [createdId, setCreatedId] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [epoch, setEpoch] = useState(0)
  const creatingRef = useRef(false)
  useEffect(() => { const changed = () => setEpoch(n => n + 1); window.addEventListener('contextkey:changed', changed); return () => window.removeEventListener('contextkey:changed', changed) }, [])
  async function refreshBookings() {
    setLoading(true); setError('')
    try { setBookings(await allPages<Booking>('/bookings')); setCreationNeedsRefresh(false); setLoaded(true); setEpoch(n => n + 1) } catch (e) { setError(intakeError(e)) } finally { setLoading(false) }
  }
  async function createBooking(event: React.FormEvent) {
    event.preventDefault()
    if (identityRef.current !== 'buyer') { startBuyerBooking(); return }
    if (creatingRef.current || loading || creationNeedsRefresh || !title.trim() || Array.from(title).length > 200) return
    creatingRef.current = true; setCreating(true); setError('')
    if (selected && bookings.some(b => b.id === selected) && !window.confirm('Create another booking? Unsaved edits in the previously opened booking will be discarded.')) { creatingRef.current = false; setCreating(false); return }
    try { const b = await post<Booking>('/bookings', { title }); setBookings(old => [b, ...old]); setTitle(''); setRentalCategory(''); setCreateOpen(false); selectedRef.current = b.id; setSelected(b.id); setCreatedId(b.id); setEntry(old => ({ step: 'sources', serial: old.serial + 1 })); window.location.hash = workspaceRoute('buyer', b.id) }
    catch (e) { setCreationNeedsRefresh(true); setError(`${intakeError(e)} Refresh the saved booking list and check whether creation succeeded before retrying.`) }
    finally { creatingRef.current = false; setCreating(false) }
  }
  useEffect(() => {
    const changed = () => {
      const hash = window.location.hash.slice(1) || 'home', { id, route: localRoute } = parseWorkspaceRoute(hash)
      if (id === 'new') {
        if (identityRef.current === 'buyer') {
          lastRoute.current = 'bookings/new'; setRoute('bookings/new'); setCreateOpen(true)
          window.history.replaceState(null, '', '#bookings/new')
          requestAnimationFrame(() => document.querySelector<HTMLInputElement>('.create-sheet input')?.focus())
        } else {
          setLogin({ role: 'buyer', hash: 'bookings/new', buyerOnly: true })
          const fallback = lastRoute.current
          setRoute(fallback); window.history.replaceState(null, '', fallback === 'home' ? location.pathname + location.search : `#${fallback}`)
        }
        return
      }
      if (localRoute.startsWith('bookings') && identityRef.current !== parseWorkspaceRoute(hash).workspace) {
        setLogin({ role: parseWorkspaceRoute(hash).workspace, hash })
        const fallback = lastRoute.current
        setRoute(fallback); window.history.replaceState(null, '', fallback === 'home' ? location.pathname + location.search : `#${fallback}`)
        return
      }
      if (id && id !== 'new' && id !== selectedRef.current) {
        if (selectedRef.current && !window.confirm('Open another booking? Unsaved edits in the previously opened booking will be discarded.')) { window.location.hash = lastRoute.current === 'home' ? '' : lastRoute.current; return }
        selectedRef.current = id; setSelected(id); setEntry(old => ({ step: 'overview', serial: old.serial + 1 }))
      }
      lastRoute.current = hash; setRoute(hash)
    }
    window.addEventListener('hashchange', changed); changed()
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  const canReadBookings = !!identity && workspace === identity && route.startsWith('bookings')
  useEffect(() => {
    if (!canReadBookings || loaded) return
    const c = new AbortController(); setLoading(true)
    allPages<Booking>('/bookings', c.signal).then(b => { if (!c.signal.aborted) { setBookings(b); setLoaded(true); setLoading(false) } }).catch(e => { if (!c.signal.aborted) { setError(intakeError(e)); setLoading(false) } })
    return () => c.abort()
  }, [canReadBookings, loaded])
  function openBooking(id: string, step: Step) {
    if (selected && selected !== id && bookings.some(b => b.id === selected) && !window.confirm('Open another booking? Unsaved edits in the previously opened booking will be discarded.')) return
    selectedRef.current = id; setSelected(id); setEntry(old => ({ step, serial: old.serial + 1 })); window.location.hash = workspaceRoute(workspace, id)
  }
  function startBuyerBooking() {
    if (creatingRef.current) return
    if (identityRef.current !== 'buyer') { setLogin({ role: 'buyer', hash: 'bookings/new', buyerOnly: true }); return }
    setCreateOpen(true); setRoute('bookings/new'); lastRoute.current = 'bookings/new'; window.location.hash = 'bookings/new'
    requestAnimationFrame(() => document.querySelector<HTMLInputElement>('.create-sheet input')?.focus())
  }
  function switchWorkspace(view: Workspace, step?: Step, selector?: string) {
    const hash = workspaceRoute(view, route === `bookings/${selected}` && selected ? selected : '')
    if (identity !== view) { setLogin({ role: view, hash, step, selector }); return }
    if (step) setEntry(old => ({ step, selector, serial: old.serial + 1 }))
    setRoute(hash); window.location.hash = hash
  }
  async function enterDemo(role: Workspace) {
    const request = login!
    if (request.buyerOnly && role !== 'buyer') return
    const fresh = await enterServerSession(() => (!selected && !title.trim()) || window.confirm('The old isolated session has ended. Start a new empty workspace? Unsaved work will be discarded; old saved records remain preserved and inaccessible to this new session.'))
    if (fresh) { setBookings([]); setLoaded(false); setSelected(''); selectedRef.current = ''; setTitle(''); setRentalCategory(''); setCreatedId('') }
    const id = parseWorkspaceRoute(request.hash).id
    const hash = workspaceRoute(role, id || '')
    identityRef.current = role; setIdentity(role)
    setSessionNotice(retainDemoRole(role) ? '' : 'Tab storage is unavailable. Demo identity lasts until this page reloads.')
    if (request.step && role === request.role) setEntry(old => ({ step: request.step!, selector: request.selector, serial: old.serial + 1 }))
    setLogin(null); setRoute(hash); lastRoute.current = hash; window.location.hash = hash
    if (id === 'new') setCreateOpen(true)
    requestAnimationFrame(() => document.querySelector<HTMLElement>(id === 'new' ? '.create-sheet input' : '.bookings-page:not([hidden]) h1')?.focus({ preventScroll: true }))
  }
  async function signOut() {
    if (!window.confirm('Sign out and end this isolated demo session? Saved records remain preserved but will not be accessible from a new session. Unsaved work in this tab will be discarded.')) return
    try { await leaveServerSession() } catch (e) { setSessionNotice(intakeError(e)); return }
    focusAfterSignOut.current = true
    retainDemoRole(null); identityRef.current = null; setIdentity(null); setLogin(null)
    setSelected(''); selectedRef.current = ''; setCreatedId(''); setCreationNeedsRefresh(false); setBookings([]); setLoaded(false); setTitle(''); setRentalCategory(''); setCreateOpen(false); setError(''); setSessionNotice('')
    lastRoute.current = 'home'; setRoute('home'); window.location.hash = ''
  }
  const inBooking = !!identity && identity === workspace && route === `bookings/${selected}` && !!selected && bookings.some(b => b.id === selected)
  const inBookings = !!identity && identity === workspace && route.startsWith('bookings')
  useEffect(() => { document.title = inBookings ? `BeforePay | ${workspace === 'buyer' ? 'Buyer' : 'Merchant'} ${inBooking ? 'workspace' : 'dashboard'}` : 'BeforePay | Know what you’re agreeing to, before you pay.' }, [inBookings, inBooking, workspace])
  const booking = bookings.find(b => b.id === selected)
  return <div className="app-shell" data-workspace={inBookings ? workspace : undefined}><a className="skip-link" href="#main-content">Skip to content</a>
    <header className={`app-header ${inBookings ? 'private-header' : 'public-header'}`}><a className="wordmark" href="#"><Brand /></a><nav className="global-nav" aria-label="Product navigation"><a href="#" aria-current={!inBookings ? 'page' : undefined}>How it works</a>{inBookings ? <a className="dashboard-link" href={`#${workspaceRoute(identity!)}`}>Dashboard</a> : <button className="primary login-entry" onClick={() => setLogin({ role: identity || 'buyer', hash: workspaceRoute(identity || 'buyer') })}>Log in</button>}</nav>{inBookings && <><span className="header-role">{workspace === 'buyer' ? 'Buyer' : 'Merchant'} demo view</span><span className="environment-label">Sandbox · test funds only<small>No real authentication</small></span></>}</header>
    {!inBookings && <EntryPage onLogin={() => setLogin({ role: identity || 'buyer', hash: workspaceRoute(identity || 'buyer') })} onStart={startBuyerBooking} />}
    {sessionNotice && <p className="notice attention" role="status">{sessionNotice}</p>}
    <div className="booking-session" hidden={!inBooking}>{identity && selected && booking && <BookingJourney created={createdId === booking.id} onSignOut={signOut} workspace={workspace} onSwitch={switchWorkspace} key={selected} booking={booking} epoch={epoch} entry={entry} active={inBooking} onBack={() => { window.location.hash = workspaceRoute(workspace) }} />}</div>
    <div className="dashboard-layout journey-layout" hidden={!inBookings || inBooking}>{identity && <aside className="dashboard-sidebar journey-rail"><div className="rail-content"><p className="rail-caption">{identity.toUpperCase()} DEMO</p><nav aria-label="Dashboard navigation"><a href={`#${workspaceRoute(identity)}`} aria-current="page">Dashboard</a><button onClick={() => { const list = document.querySelector<HTMLElement>(".bookings-page .dashboard-list-heading"); list?.scrollIntoView({ block: "start" }); list?.focus({ preventScroll: true }) }}>Shared bookings</button></nav></div><DemoIdentity role={identity} onSwitch={() => setLogin({ role: identity === "buyer" ? "merchant" : "buyer", hash: workspaceRoute(identity === "buyer" ? "merchant" : "buyer") })} onSignOut={signOut} /></aside>}<main className="bookings-page" id={inBookings && !inBooking ? 'main-content' : undefined} hidden={!inBookings || inBooking}>
      <div className="page-heading"><div><p className="eyebrow">{workspace === "buyer" ? "BUYER WORKSPACE" : "MERCHANT WORKSPACE"}</p><h1 tabIndex={-1}>{workspace === "buyer" ? "Buyer dashboard" : "Merchant dashboard"}</h1><p>{workspace === "buyer" ? "Your rentals, review progress and recorded payments." : "Shared bookings, final proposals, merchant policy review and recorded payments."}</p><p className="hint">Prototype views—not authenticated accounts. Both workspaces use the same bookings.</p></div><button className={createOpen && workspace === "buyer" ? undefined : 'primary'} onClick={() => { if (createOpen && workspace === "buyer") setCreateOpen(false); else startBuyerBooking() }}>{createOpen && workspace === "buyer" ? 'Close form' : 'Create booking'}</button></div>
      <section className={`dashboard-guide ${workspace}`} aria-label={workspace === 'buyer' ? 'Buyer tasks' : 'Merchant tasks'}><h2>{workspace === 'buyer' ? 'Know your terms before you pay.' : 'Prepare a final booking the buyer can review.'}</h2><p>{workspace === 'buyer' ? 'Start with your quotation and messages. Confirm the exact agreement, review the merchant’s changes, then approve sandbox checkout separately.' : 'Use the buyer-confirmed terms as reference. Save your independent final proposal, review its cancellation rules and follow the buyer handoff.'}</p><ol>{(workspace === 'buyer' ? ['Evidence and agreement review','Differences and cancellation consequences','Checkout approval and receipt'] : ['Buyer reference and final proposal','Merchant policy preparation and review','Buyer handoff and recorded payment']).map(task => <li key={task}>{task}</li>)}</ol></section>
      <div className="dashboard-list-heading" tabIndex={-1}><h2>{workspace === 'buyer' ? 'Rentals and next actions' : 'Proposal and policy work queue'}</h2><p>Shared bookings · statuses below come from saved records.</p></div>
      {loaded && !loading && route !== 'bookings' && route !== 'bookings/new' && !inBooking && <p className="notice attention" role="alert">The requested booking is not in the saved list. Choose an available booking below or create a new one.</p>}
      {createOpen && identity === "buyer" && workspace === "buyer" && <section className="create-sheet"><h2>A new rental booking</h2><p>Name the rental, then add your quotation and messages. No equipment or terms are added automatically.</p><form onSubmit={e => void createBooking(e)}><label>Rental category · setup guide<select value={rentalCategory} disabled={creating} aria-describedby="rental-category-help" onChange={e => setRentalCategory(e.target.value as RentalCategory | '')}><option value="">Choose a rental category</option>{Object.entries(rentalCategories).map(([key, category]) => <option key={key} value={key}>{category.label}</option>)}</select><small id="rental-category-help">Guides naming only; category is not stored as an agreement term. Saved sources establish the actual items.</small></label><label>Booking title<input autoFocus value={title} maxLength={200} required disabled={creating} placeholder={rentalCategory ? rentalCategories[rentalCategory].example : 'e.g. Equipment rental · event or project'} aria-describedby="booking-title-help" onChange={e => setTitle(e.target.value)} /><small id="booking-title-help">Use your own equipment names. This title does not create equipment, prices or policies.</small></label><Action className="primary" disabled={creating || loading || creationNeedsRefresh || !title.trim()} reason={creating ? 'Creating your booking…' : loading ? 'Wait for the saved booking list to finish loading.' : creationNeedsRefresh ? 'Refresh the saved list and check for your booking before retrying.' : 'Enter a booking name to continue.'}>Create booking</Action></form></section>}
      {error && <p className="notice error" role="alert">{error}</p>}
      <div className="list-toolbar"><span>{loading ? 'Loading bookings…' : `${bookings.length} saved booking${bookings.length === 1 ? '' : 's'}`}</span><button disabled={loading || creating} onClick={() => void refreshBookings()}>Refresh list</button></div>
      {!!bookings.length && <div className="booking-table" tabIndex={-1}><table className="data-table bookings-table"><caption className="sr-only">Saved bookings, rental dates, inclusive totals, statuses and next actions</caption><colgroup><col className="booking-col-name" /><col className="booking-col-dates" /><col className="booking-col-total" /><col className="booking-col-status" /><col className="booking-col-action" /></colgroup><thead><tr><th scope="col">Booking / equipment</th><th scope="col">{workspace === "buyer" ? "Pickup & return" : "Buyer agreement"}</th><th scope="col" className={workspace === "buyer" ? "numeric" : undefined}>{workspace === "buyer" ? "Inclusive total" : "Merchant proposal / rules"}</th><th scope="col">Current status</th><th scope="col" className="table-actions">Next action</th></tr></thead><tbody>{bookings.map(b => <BookingRow active={inBookings && !inBooking} key={b.id} booking={b} epoch={epoch} workspace={workspace} onOpen={step => openBooking(b.id, step)} />)}</tbody></table></div>}
      {!loading && !error && !bookings.length && <section className="empty-state" tabIndex={-1}><span className="empty-document" aria-hidden="true">01</span><h2>Your next rental starts here.</h2><p>Create a booking, add the agreed quotation, then check the final terms side by side. Nothing is generated or approved automatically.</p><button onClick={startBuyerBooking}>Create your first booking</button></section>}
    </main></div>
    {login && <DemoLogin key={login.buyerOnly ? "booking-entry" : "role-entry"} requiredRole={login.buyerOnly ? "buyer" : undefined} currentRole={identity} initialRole={login.role} onEnter={enterDemo} onDismiss={() => setLogin(null)} />}
    <footer className="app-footer"><span>BeforePay · Local prototype</span><span>Identity is provisional. Workspaces are not authenticated roles.</span></footer>
  </div>
}
const merchantSteps: typeof steps = [
  { id: 'overview', label: 'Merchant overview', detail: 'Preparation and handoff' },
  { id: 'reference', label: 'Buyer reference', detail: 'Read-only agreed terms' },
  { id: 'comparison', label: 'Final proposal', detail: 'Create or revise merchant version' },
  { id: 'clarifications', label: 'Clarification replies', detail: 'Questions and provisional responses' },
  { id: 'cancellation', label: 'Merchant policy rules', detail: 'Prepare and review proposal rules' },
  { id: 'checkout', label: 'Payment status', detail: 'Recorded sandbox captures' },
]
function BookingJourney({ booking, epoch, entry, active, onBack, workspace, onSwitch, onSignOut, created }: { created: boolean; onSignOut: () => void; active: boolean; booking: Booking; epoch: number; entry: { step: Step; serial: number; selector?: string }; onBack: () => void; workspace: Workspace; onSwitch: (view: Workspace, step?: Step, selector?: string) => void }) {
  const [buyerTab, setBuyerTab] = useState<Step>(workspace === 'buyer' ? entry.step : 'overview')
  const [merchantTab, setMerchantTab] = useState<Step>(workspace === 'merchant' ? entry.step : 'overview')
  const tab = workspace === 'buyer' ? buyerTab : merchantTab
  const [visited, setVisited] = useState<Set<string>>(new Set(['overview', `${workspace}:${entry.step}`]))
  const [findingsSerial, setFindingsSerial] = useState(0)
  const [ruleRequest, setRuleRequest] = useState<{ serial: number; kind: 'agreement' | 'proposal'; workspace: Workspace }>()
  const [revision, setRevision] = useState(0)
  const { snapshot, error } = useSnapshot(booking.id, epoch + revision, active)
  useEffect(() => { const update = () => setRevision(n => n + 1); window.addEventListener('contextkey:changed', update); return () => window.removeEventListener('contextkey:changed', update) }, [])
  function focus(selector?: string) { requestAnimationFrame(() => { const main = document.querySelector<HTMLElement>('#main-content'); main?.scrollIntoView({ block: 'start' }); if (window.matchMedia('(max-width: 1023px)').matches) document.querySelector<HTMLButtonElement>('.tabs button[aria-current=step]')?.scrollIntoView({ block: 'nearest', inline: 'center' }); const target = selector ? main?.querySelector<HTMLElement>(`.workspace-host:not([hidden]) ${selector}`) : main?.querySelector<HTMLElement>('h1, .completed-receipt h2'); if (target) { for (let p: HTMLElement | null = target; p; p = p.parentElement) if (p instanceof HTMLDetailsElement) p.open = true; target.tabIndex = -1; if (selector) target.scrollIntoView({ block: 'start' }); target.focus({ preventScroll: true }) } }) }
  function openIn(view: Workspace, step: Step, selector?: string) {
    setVisited(v => new Set([...v, `${view}:${step}`]))
    if (view === 'buyer') setBuyerTab(step); else setMerchantTab(step)
    if (view !== workspace) { onSwitch(view, step, selector || (view === 'merchant' && step === 'comparison' ? '.merchant-editor > summary' : undefined)); return }
    focus(selector)
  }
  function navigateBlocker(to: Destination) {
    if (to.selector === '.policy-consistency') setFindingsSerial(n => n + 1)
    if (to.kind) setRuleRequest(old => ({ serial: (old?.serial ?? 0) + 1, kind: to.kind!, workspace: to.workspace }))
    openIn(to.workspace, to.step, to.selector)
  }
  function go(step: Step, selector?: string) { openIn(workspace === 'merchant' && (step === 'review' || step === 'sources') ? 'buyer' : workspace, step, selector) }
  useEffect(() => { go(entry.step, entry.selector) }, [entry.serial])
  useEffect(() => {
    const frame = requestAnimationFrame(() => { if (window.matchMedia('(max-width: 1023px)').matches) document.querySelector('.tabs button[aria-current=step]')?.scrollIntoView({ block: 'nearest', inline: 'center' }) })
    return () => cancelAnimationFrame(frame)
  }, [workspace])
  useEffect(() => {
    if (!active) return
    const main = document.querySelector<HTMLElement>('#main-content')
    const rail = document.querySelector('.booking-session .journey-rail')
    const header = document.querySelector('.app-header')
    if (!main || !rail || !header) return
    const update = () => main.style.setProperty('--workspace-offset', `${header.getBoundingClientRect().height + (matchMedia('(max-width: 1023px)').matches && getComputedStyle(rail).position === 'sticky' ? rail.getBoundingClientRect().height : 0) + 16}px`)
    const observer = new ResizeObserver(update); observer.observe(rail); observer.observe(header); update()
    return () => observer.disconnect()
  }, [active, workspace])
  const navSteps = workspace === 'buyer' ? steps : merchantSteps
  const next = snapshot && !error ? workspaceNext(snapshot, workspace) : null
  const state = (step: Step) => {
    if (error) return { label: 'Saved state unavailable', tone: 'attention' }
    if (workspace === 'buyer' || !snapshot || step === 'reference') return stageState(error ? null : snapshot, step)
    if (step === 'overview') return { label: 'Preparation & handoff', tone: 'neutral' }
    if (step === 'clarifications') return stageState(snapshot, step)
    if (step === 'comparison') return { label: snapshot.proposal ? `Saved version ${snapshot.proposal.version}` : 'Merchant proposal needed', tone: snapshot.proposal ? 'success' : 'attention' }
    if (step === 'cancellation') { const ok = snapshot.rules.some(r => r.target.kind === 'proposal' && r.target.id === snapshot.proposal?.id && r.approved_current); return { label: ok ? 'Merchant rules reviewed' : 'Merchant rule review needed', tone: ok ? 'success' : 'attention' } }
    if (snapshot.receipt) return { label: 'Capture recorded · sandbox', tone: 'success' }
    if (snapshot.attempts.length) return { label: 'Check recorded attempts', tone: 'attention' }
    return { label: 'No payment recorded', tone: 'neutral' }
  }
  const buyer = (step: Step) => openIn('buyer', step)
  const needs = (view: Workspace, step: Step) => visited.has(`${view}:${step}`)
  const readOnly = (content: React.ReactNode) => error ? <p className="notice error" role="alert">Saved state unavailable. {error}<button onClick={() => setRevision(n => n + 1)}>Retry saved state</button></p> : snapshot ? content : <p role="status">Reading saved booking state…</p>
  return <BlockerContext.Provider value={{ workspace, step: tab, snapshot, navigate: navigateBlocker, ruleRequest, findingsSerial }}><JourneyContext.Provider value={go}><EvidenceProvider bookingId={booking.id}><div className="journey-layout"><aside className="journey-rail"><div className="rail-content"><button className="back-link" onClick={onBack}>← All bookings</button><p className="rail-caption">{workspace.toUpperCase()} WORKSPACE</p><nav className="tabs" aria-label={`${workspace === 'buyer' ? 'Buyer' : 'Merchant'} booking workflow`}>{navSteps.map((s, index) => <button key={s.id} aria-label={`${s.label}: ${state(s.id).label}`} aria-current={tab === s.id ? 'step' : undefined} aria-pressed={tab === s.id} onClick={() => go(s.id)}><span className="step-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span><span><span className="nav-symbol" aria-hidden="true">{state(s.id).tone === 'success' ? '✓' : ['blocked','attention'].includes(state(s.id).tone) ? '!' : '·'}</span>{s.label}<small className={`nav-state tone-${state(s.id).tone}`}>{state(s.id).tone === 'success' ? '✓ ' : ''}{state(s.id).label}</small></span></button>)}</nav><div className="rail-next"><p className="eyebrow">NEXT MEANINGFUL ACTION</p><p>{next?.label || (error ? 'Saved state unavailable' : 'Checking saved state…')}</p>{next && next.step !== tab && <BlockerNext codes={snapshot?.receipt || snapshot?.attempts.length ? [] : snapshot?.blockers ?? []} fallback={<button onClick={() => go(next.step)}>Go to next task →</button>} />}</div></div><DemoIdentity role={workspace} onSwitch={() => onSwitch(workspace === "buyer" ? "merchant" : "buyer")} onSignOut={onSignOut} /></aside>
    <main className="journey-main" id={active ? 'main-content' : undefined}><div className="workspace-view-switch"><div><strong>{workspace === 'buyer' ? 'Buyer' : 'Merchant'} workspace</strong><small>Prototype views—not authenticated accounts</small></div><div role="group" aria-label="Switch prototype workspace"><button aria-pressed={workspace === 'buyer'} onClick={() => onSwitch('buyer')}>Buyer workspace</button><button aria-pressed={workspace === 'merchant'} onClick={() => onSwitch('merchant')}>Merchant workspace</button></div></div>
      {(workspace === 'merchant' || tab !== 'checkout' || !snapshot?.receipt) && <div className="booking-heading"><div><p className="workspace-location">Stage {navSteps.findIndex(s => s.id === tab) + 1} of {navSteps.length} · {navSteps.find(s => s.id === tab)?.label}</p><h1>{booking.title}</h1></div><span className="perspective-label">{workspace === 'buyer' ? 'Buyer perspective' : 'Merchant perspective'}<small>Same booking · separate saved versions</small></span></div>}
      {created && workspace === 'buyer' && tab === 'sources' && <p className="notice success" role="status"><strong>Booking created.</strong> Next: add your original quotation, messages or PDF in Sources &amp; draft. AI draft generation is a separate explicit action.</p>}
      {tab === 'overview' && (workspace === 'buyer' ? <Overview snapshot={snapshot} error={error} go={go} refresh={() => setRevision(n => n + 1)} /> : readOnly(snapshot && <MerchantOverview snapshot={snapshot} go={go} buyer={buyer} />))}
      {['sources','review','checkout'].filter(s => needs('buyer', s as Step)).map(s => <WorkspaceFrame key={s} active={active && workspace === 'buyer' && tab === s}>{s === 'sources' ? <EvidenceWorkspace bookingId={booking.id} onReview={() => go('review')} /> : s === 'review' ? <ReviewWorkspace bookingId={booking.id} /> : <CheckoutWorkspace bookingId={booking.id} bookingTitle={booking.title} />}</WorkspaceFrame>)}
      {(needs('buyer','comparison') || needs('merchant','comparison')) && <WorkspaceFrame active={active && tab === 'comparison'}><ComparisonWorkspace bookingId={booking.id} view={workspace} onViewChange={view => openIn(view, 'comparison')} /></WorkspaceFrame>}
      {(['buyer','merchant'] as const).filter(view => needs(view,'cancellation')).map(view => <WorkspaceFrame key={`${view}-rules`} active={active && workspace === view && tab === 'cancellation'}><CancellationWorkspace bookingId={booking.id} merchant={view === 'merchant'} /></WorkspaceFrame>)}
      {needs('merchant','clarifications') && <WorkspaceFrame active={active && workspace === 'merchant' && tab === 'clarifications'}><MerchantClarifications bookingId={booking.id} onBuyerReview={() => buyer('comparison')} /></WorkspaceFrame>}
      {workspace === 'merchant' && tab === 'reference' && <WorkspaceFrame active={active}>{readOnly(snapshot && <BuyerReference snapshot={snapshot} buyer={buyer} />)}</WorkspaceFrame>}
      {workspace === 'merchant' && tab === 'checkout' && <WorkspaceFrame active={active}>{readOnly(snapshot && <MerchantPayment snapshot={snapshot} buyer={buyer} />)}</WorkspaceFrame>}
    </main></div></EvidenceProvider></JourneyContext.Provider></BlockerContext.Provider>
}

function Overview({ snapshot: s, error, go, refresh }: { snapshot: Snapshot | null; error: string; go: (step: Step) => void; refresh: () => void }) {
  if (error) return <div className="notice error" role="alert">Could not load booking overview. {error}<button onClick={refresh}>Retry overview</button></div>
  if (!s) return <p role="status">Reading saved booking status…</p>
  const next = nextStep(s), claims = snapshotClaims(s)!
  const capturedCurrentAgreement = !s.receipt || s.receipt.context?.agreement_id === s.agreement?.id
  const oneMoney = (kind: string) => { const values = claims?.amounts?.filter(c => c.kind === kind); return values?.length === 1 && !values[0].ambiguous ? money(values[0].amount, values[0].currency) : 'Not specified / unresolved' }
  return <div className="overview-layout"><div><section className={`next-action next-${next.tone}`}><p className="eyebrow">YOUR NEXT STEP</p><h2><Status tone={next.tone}>{next.status}</Status></h2><p className="mobile-total">Inclusive total <strong>{s.receipt ? money(s.receipt.amount, s.receipt.currency) : oneMoney('total_payable')}</strong></p><p>{next.detail}</p><BlockerNext codes={s.receipt || s.attempts.length ? [] : s.blockers} fallback={<button className="primary" onClick={() => go(next.step)}>{next.label} <span aria-hidden="true">→</span></button>} /></section>
    <section className="document-section"><div className="section-heading"><h2>Your rental</h2><button onClick={() => go('review')}>View agreement</button></div><p className="hint">{s.review.confirmation_current ? 'Current confirmed agreement' : s.agreement ? 'Saved agreement · not currently confirmed' : s.proposal ? 'Merchant proposal · no confirmed baseline' : 'No terms saved yet'}</p><h3>Equipment & included items</h3>{claims?.equipment?.length ? claims.equipment.map((c, i) => <p className="rental-item" key={i}>{describeClaim(c)}</p>) : <p>Equipment not specified</p>}{claims?.included_items?.map((c, i) => <p className="hint" key={i}>Included: {describeClaim(c)}</p>)}<dl className="date-ledger"><div><dt>Pickup</dt><dd>{claims?.pickup?.length === 1 && !claims.pickup[0].ambiguous ? humanTime(claims.pickup[0].value) : 'Not specified / unresolved'}</dd></div><div><dt>Return</dt><dd>{claims?.return_time?.length === 1 && !claims.return_time[0].ambiguous ? humanTime(claims.return_time[0].value) : 'Not specified / unresolved'}</dd></div></dl></section>
    <section className="document-section overview-tasks"><h2>Outstanding tasks & history</h2><div className="progress-row"><span>Agreement</span><strong>{s.review.confirmation_current ? 'Confirmed' : 'Review required'}</strong><button onClick={() => go('review')}>Review terms</button></div><div className="progress-row"><span>Final booking</span><strong>{!s.comparison ? 'Not compared' : s.comparison.stale ? 'Comparison out of date' : s.comparison.results.some(r => r.status !== 'matches') ? 'Differences / clarification' : s.comparison.results.length ? 'Compared · matching' : 'No comparison results'}</strong><button onClick={() => go('comparison')}>Review comparison</button></div><div className="progress-row"><span>Cancellation</span><strong>{['agreement', 'proposal'].every(kind => s.rules.some(r => r.target.kind === kind && r.target.id === (kind === 'agreement' ? s.agreement?.id : s.proposal?.id) && r.approved_current)) ? 'Both policies reviewed' : 'Rule review required'}</strong><button onClick={() => go('cancellation')}>Review rules</button></div><div className="progress-row"><span>Payment</span><strong>{s.receipt ? 'Paid · sandbox' : s.attempts.length ? s.attempts[0].status.replaceAll('_', ' ') : 'Not started'}</strong><button onClick={() => go('checkout')}>{s.receipt ? 'View receipt' : 'Review checkout'}</button></div></section></div>
    <aside className="financial-ledger"><p className="eyebrow">BOOKING TOTAL</p><dl>{!s.receipt && <><div><dt>Rental fee</dt><dd>{oneMoney('rental_total')}</dd></div><div><dt>Deposit</dt><dd>{oneMoney('deposit')}</dd></div></>}<div className="ledger-total"><dt>{s.receipt ? 'Captured inclusive total' : 'Inclusive total'}</dt><dd>{s.receipt ? money(s.receipt.amount, s.receipt.currency) : oneMoney('total_payable')}</dd></div></dl><p className="hint">Inclusive total is already the stated total, not another charge.</p>{s.receipt && <p className="success">Completed sandbox capture recorded.{!capturedCurrentAgreement && ' The current agreement differs from the captured version; use the receipt for payment history.'}</p>}<button onClick={() => go('cancellation')}>What if I cancel?</button>{s.blockers.length > 0 && !s.receipt && <details className="help"><summary>What still needs attention?</summary><BlockerList codes={s.blockers} /></details>}<p className="hint">Sandbox · no real funds.<br />Payment eligibility is checked by the backend.</p></aside>
  </div>
}
