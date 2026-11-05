import { BlockerList } from './BlockerActions'
import { WorkspaceReadContext } from './WorkspaceFrame'
import TechnicalDetails from './TechnicalDetails'
import { Action, Resolve, TaskIntro, Status } from './product-ui'
import SandboxReceipt, { type CaptureReceipt } from './SandboxReceipt'
import { useContext, useEffect, useRef, useState } from 'react'
import { blockerText, friendlyError } from './conditions'
import { ApiError, post, request } from './review-api'
import { sandboxSdk } from './paypal-sdk'

type Context = { environment: 'sandbox'; agreement_id: string; agreement_version: number; agreement_fingerprint: string; proposal_id: string; proposal_version: number; proposal_fingerprint: string; comparison_id: string; comparison_fingerprint: string; amount: string; currency: string }
type Eligibility = { eligible: boolean; blockers: string[]; context: Context | null; fingerprint: string | null; sandbox_configured: boolean; payment_execution_allowed?: boolean; payment_notice?: string | null }
type Approval = { id: string; fingerprint: string; context: Context }
type Attempt = { id: string; approval_id: string; amount: string; currency: string; status: string; error_code: string | null; order_id: string | null; capture_id: string | null }
type Receipt = CaptureReceipt
const labels: Record<string, string> = { creating: 'Pending order creation', create_uncertain: 'Pending: order outcome uncertain', awaiting_buyer: 'Awaiting buyer approval', capture_uncertain: 'Pending: capture outcome uncertain', pending: 'Pending PayPal processing', failed: 'Failed', cancelled: 'Cancelled', blocked: 'Blocked', completed: 'Completed sandbox capture' }

export default function CheckoutWorkspace({ bookingId, bookingTitle = '' }: { bookingId: string; bookingTitle?: string }) {
  const markRead = useContext(WorkspaceReadContext)
  const base = `/bookings/${bookingId}/checkout`
  const [eligibility, setEligibility] = useState<Eligibility | null>(null)
  const [approval, setApproval] = useState<Approval | null>(null)
  const [history, setHistory] = useState<Attempt[]>([])
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [actor, setActor] = useState('')
  const [ack, setAck] = useState(false)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [sdkReady, setSdkReady] = useState(false)
  const [blocked, setBlocked] = useState(false)
  const container = useRef<HTMLDivElement>(null)
  const currentAttempt = useRef<Attempt | null>(null)
  const mounted = useRef(true)
  const action = useRef(false)
  const buyerOpen = useRef(false)
  function update(a: Attempt | null) { currentAttempt.current = a; if (mounted.current) setAttempt(a) }
  const paymentRequest = <T,>(path: string, body: unknown = {}) => request<T>(`${base}${path}`, { method: 'POST', body: JSON.stringify(body), signal: AbortSignal.timeout(120000) })
  async function fetchReceipt() {
    const r = await request<Receipt>(`${base}/receipt`)
    if (mounted.current) setReceipt(r)
  }
  async function load(signal?: AbortSignal) {
    const [e, attempts] = await Promise.all([request<Eligibility>(`${base}/eligibility`, { signal }), request<Attempt[]>(`${base}/attempts`, { signal })])
    if (!mounted.current || signal?.aborted) return
    setEligibility(e); setHistory(attempts); update(attempts[0] ?? null)
    if (attempts.some(a => a.status === 'completed')) await fetchReceipt()
    setApproval(null); setAck(false); setBlocked(!e.eligible); setSdkReady(false); container.current?.replaceChildren(); markRead()
  }
  useEffect(() => { mounted.current = true; const c = new AbortController(); load(c.signal).catch(e => { if (!c.signal.aborted) setError(e.message) }).finally(() => { if (!c.signal.aborted) setBusy(false) }); return () => { mounted.current = false; c.abort() } }, [])
  async function act(work: () => Promise<void>) {
    if (action.current) return
    action.current = true; setBusy(true); setError(''); setMessage('')
    try { await work() } catch (e) { if (mounted.current) { setError(e instanceof Error ? e.message : 'Sandbox request failed.'); if (e instanceof ApiError && e.status === 409) { setBlocked(true); setAck(false); setSdkReady(false); container.current?.replaceChildren() } } }
    finally { action.current = false; if (mounted.current) setBusy(false) }
  }
  async function afterAttempt(a: Attempt) {
    update(a); setHistory(old => [a, ...old.filter(x => x.id !== a.id)])
    if (a.status !== 'awaiting_buyer') { setSdkReady(false); container.current?.replaceChildren() }
    if (a.status === 'completed') { await fetchReceipt(); setSdkReady(false); container.current?.replaceChildren() }
    if (a.status === 'cancelled') { setApproval(null); setAck(false); setSdkReady(false); container.current?.replaceChildren() }
  }
  async function approve() {
    if (!eligibility?.fingerprint || !eligibility.eligible || !ack) return
    await act(async () => {
      const a = await post<Approval>(`${base}/approvals`, { expected_context_fingerprint: eligibility.fingerprint, customer_label: actor, acknowledged: true })
      setApproval(a); setMessage('Checkout approval saved for these exact versions. No order or payment created yet.')
    })
  }
  async function setup() {
    if (!approval) return
    await act(async () => {
      const config = await request<{ environment: string; client_id: string | null; sdk_url: string; configured: boolean }>(`${base}/config`)
      if (config.environment !== 'sandbox' || !config.configured || !config.client_id) throw new Error('Configure backend PayPal sandbox credentials first.')
      const sdk = await sandboxSdk(config.client_id)
      const methods = await sdk.findEligibleMethods({ currencyCode: approval.context.currency, amount: approval.context.amount })
      if (!methods.isEligible('paypal')) throw new Error('PayPal sandbox buyer approval is not available in this browser/account.')
      let orderPromise: Promise<{ orderId: string }> | null = null
      const session = sdk.createPayPalOneTimePaymentSession({
        onApprove: async data => {
          buyerOpen.current = false
          if (!mounted.current) return
          const a = currentAttempt.current
          if (!a || a.order_id !== data.orderId) { setError('PayPal approval does not match the saved order. Refresh and reconcile.'); setBusy(false); return }
          await act(async () => { await afterAttempt(await paymentRequest<Attempt>(`/attempts/${a.id}/capture`)) })
        },
        onCancel: async () => {
          buyerOpen.current = false
          if (!mounted.current) return
          try { await orderPromise } catch { /* Failed creation stays pending for reconciliation. */ }
          const a = currentAttempt.current
          if (a) await act(async () => { await afterAttempt(await paymentRequest<Attempt>(`/attempts/${a.id}/cancel`)) })
          else { setMessage('Buyer cancelled before a sandbox order was created.'); setBusy(false) }
        },
        onError: () => { buyerOpen.current = false; if (!mounted.current) return; setError('PayPal buyer flow failed or was interrupted. Reconcile any saved attempt before retrying.'); setBusy(false) },
      })
      const button = document.createElement('paypal-button')
      button.setAttribute('type', 'pay')
      button.addEventListener('click', () => {
        if (action.current || buyerOpen.current || !mounted.current) return
        buyerOpen.current = true; setBusy(true)
        setError(''); setMessage('Opening PayPal sandbox buyer approval…')
        orderPromise = paymentRequest<Attempt>('/orders', { approval_id: approval.id }).then(a => {
          update(a); setHistory(old => [a, ...old.filter(x => x.id !== a.id)])
          if (!a.order_id || !['awaiting_buyer'].includes(a.status)) throw new Error('Order is pending or unavailable. Reconcile before retrying.')
          return { orderId: a.order_id }
        })
        void session.start({ presentationMode: 'popup' }, orderPromise).catch(() => { buyerOpen.current = false; if (mounted.current) { setBusy(false); setError('Could not finish buyer approval. Inspect the saved attempt and reconcile before retrying.') } })
      })
      container.current?.replaceChildren(button); setSdkReady(true)
      setMessage('Sandbox PayPal button ready. Clicking it explicitly creates/reuses this approved checkout order.')
    })
  }
  const paymentsDisabled = eligibility?.payment_execution_allowed === false
  const paymentDisabledReason = 'Payments and provider reconciliation are disabled in the public demo.'
  const active = attempt && ['creating', 'create_uncertain', 'awaiting_buyer', 'capture_uncertain', 'pending'].includes(attempt.status)
  return <section className="workspace checkout-workspace" aria-busy={busy}>
    <div className={receipt ? 'toolbar receipt-tools' : 'toolbar'}>{!receipt && <div><h2>Sandbox checkout</h2><p>Review the total, approve checkout, then continue to PayPal.</p></div>}<button disabled={busy} onClick={() => void act(() => load())}>Refresh</button></div>
    {busy && <p role="status">Checking / processing sandbox checkout…</p>}{error && <div className="notice error" role="alert">{friendlyError(error)}{friendlyError(error) !== error && <TechnicalDetails label="Error details" data={{ error }} />}</div>}{message && <p className="notice success" role="status">{message}</p>}
    {!receipt && <TaskIntro owner={paymentsDisabled ? "Buyer checkout · public demo" : "Buyer checkout · sandbox"} title={paymentsDisabled ? "Review checkout readiness · payments disabled" : "Approve the agreement bundle, then pay"}>Checkout approval binds the exact agreement, merchant proposal, comparison and reviewed policies. PayPal buyer approval alone is not captured payment.</TaskIntro>}
    {attempt && !receipt && <section className={`panel payment-attempt ${active ? 'payment-pending' : ''}`}><div className="attempt-heading"><h3>{labels[attempt.status] ?? attempt.status}</h3><p className="attempt-amount">{attempt.currency} {attempt.amount}</p></div><TechnicalDetails label="Payment details" data={{ attempt_id: attempt.id, order_id: attempt.order_id, capture_id: attempt.capture_id, status: attempt.status, error_code: attempt.error_code }} />{attempt.error_code && <p className="notice">{blockerText(attempt.error_code)}</p>}
      {attempt.status === 'cancelled' && <p>Buyer checkout cancelled locally. No capture is authorized from this attempt.</p>}
      {attempt.status === 'failed' && <p>PayPal reports a declined/voided payment. Refresh before making a new explicit checkout approval.</p>}
      {['create_uncertain', 'capture_uncertain', 'pending'].includes(attempt.status) && <p>Outcome is pending/uncertain, not paid. Reconcile first; never start a fresh attempt to bypass it.</p>}
      <div className="payment-attempt-actions">
      {attempt.status === 'awaiting_buyer' && !approval && <Action reason={busy ? 'Wait for the current request.' : 'Refresh and resolve checkout eligibility before restoring approval.'} disabled={busy || blocked || !eligibility?.eligible} onClick={() => void act(async () => { const a = await request<Approval & { customer_label: string }>(`${base}/approvals/${attempt.approval_id}`); setApproval(a); setActor(a.customer_label); setAck(true); setMessage('Original exact checkout approval restored. Load sandbox buyer approval to resume this order.') })}>Resume saved checkout approval</Action>}
      {attempt.order_id && attempt.status !== 'completed' && <Action reason={paymentsDisabled ? paymentDisabledReason : 'Wait for the current payment request before checking again.'} disabled={busy || paymentsDisabled} onClick={() => void act(async () => { await afterAttempt(await paymentRequest<Attempt>(`/attempts/${attempt.id}/reconcile`)) })}>Check PayPal status · no new capture</Action>}
      {attempt.status === 'capture_uncertain' && <Action reason={paymentsDisabled ? paymentDisabledReason : busy ? 'Wait for the current request.' : 'Current checkout eligibility must pass before an explicit capture retry.'} disabled={paymentsDisabled || busy || blocked || !eligibility?.eligible} onClick={() => void act(async () => { await afterAttempt(await paymentRequest<Attempt>(`/attempts/${attempt.id}/capture`, { retry_uncertain: true })) })}>Retry capture · checks status first</Action>}
      {attempt.status === 'create_uncertain' && !attempt.order_id && <Action reason={paymentsDisabled ? paymentDisabledReason : busy ? 'Wait for the current request.' : 'Current checkout eligibility must pass before retrying the original order key.'} disabled={paymentsDisabled || busy || blocked || !eligibility?.eligible} onClick={() => void act(async () => { await afterAttempt(await paymentRequest<Attempt>('/orders', { approval_id: attempt.approval_id })) })}>Retry same order request</Action>}
      {['awaiting_buyer', 'creating', 'create_uncertain'].includes(attempt.status) && <Action className="destructive" reason={'Wait for the current payment request. Cancellation cannot undo a capture.'} disabled={busy} onClick={() => void act(async () => { await afterAttempt(await paymentRequest<Attempt>(`/attempts/${attempt.id}/cancel`)) })}>Cancel checkout</Action>}
      </div>
    </section>}
    {!receipt && !active && eligibility && <section className="checkout-readiness"><h3><Status tone={eligibility.eligible && !blocked ? 'success' : 'blocked'}>{eligibility.eligible && !blocked ? 'Backend checks passed' : 'Review needed before payment'}</Status></h3><p>{eligibility.eligible && !blocked ? 'Review the exact saved versions and inclusive total below.' : 'Resolve the listed issues, then refresh. No frontend status can authorize payment.'}</p></section>}

    {eligibility?.payment_execution_allowed === false && <p className="notice" role="status">{eligibility.payment_notice || 'Payments and provider reconciliation are disabled in the public demo. Existing receipts are historical capture records.'}</p>}
    {!receipt && !eligibility?.sandbox_configured && eligibility?.payment_execution_allowed !== false && <p className="notice">Sandbox disabled or unconfigured. Set backend sandbox credentials and enable it before buyer checkout.</p>}
    {(blocked || !!eligibility?.blockers.length) && !receipt && <section className="notice error"><h3>Checkout blocked</h3><BlockerList codes={eligibility?.blockers ?? []} /><TechnicalDetails label="Issue details" data={{ blockers: eligibility?.blockers }} /><p>Resolve the listed issues, then refresh.</p></section>}
    {!receipt && (!active || attempt?.status === 'awaiting_buyer') && eligibility?.context && <section className="panel checkout-approval"><aside className="checkout-total"><p className="eyebrow">INCLUSIVE TOTAL · TEST FUNDS</p><h3>1. Review total</h3><p><strong>{eligibility.context.currency} {eligibility.context.amount}</strong>Total payable, including rental fee and deposit.</p><p>Confirmed agreement version {eligibility.context.agreement_version}<br />Merchant proposal version {eligibility.context.proposal_version}</p><TechnicalDetails data={{ checkout_fingerprint: eligibility.fingerprint, ...eligibility.context }} /></aside><div className="checkout-steps"><p className="eyebrow">EXPLICIT HUMAN APPROVAL</p><h3>2. Approve checkout</h3>
      <label>Your name / reviewer label<input value={actor} maxLength={100} disabled={busy || !!approval} onChange={e => setActor(e.target.value)} /></label><label className="check"><input type="checkbox" checked={ack} disabled={busy || !!approval || !eligibility.eligible || blocked} onChange={e => setAck(e.target.checked)} />I explicitly approve sandbox checkout for these exact agreement, proposal, comparison and reviewed policies.</label>
      <Action className="primary" disabled={busy || !eligibility.eligible || blocked || !actor.trim() || !ack || !!approval || !!receipt || !!active} resolve={!busy && !approval && eligibility.eligible && !blocked ? { label: active ? 'Review saved payment attempt' : !actor.trim() ? 'Enter reviewer name' : 'Review checkout acknowledgement', selector: active ? '.payment-attempt' : !actor.trim() ? '.checkout-steps input' : '.checkout-steps .check input' } : undefined} reason={busy ? 'Wait for the current request.' : active ? 'Resolve or resume the existing payment attempt first.' : approval ? 'Exact checkout approval already saved.' : blocked || !eligibility.eligible ? 'Resolve the backend readiness issues listed above.' : !actor.trim() ? 'Enter your reviewer name.' : 'Tick the explicit checkout acknowledgement.'} onClick={() => void approve()}>Approve sandbox checkout</Action>
      {approval && <p className="success">Explicit checkout approval saved.</p>}
      <div className="paypal-stage-label"><p className="eyebrow">SEPARATE PAYMENT ACTION</p><h3>3. Continue to PayPal</h3></div><p className="hint">Load the button, then approve with your sandbox buyer account.</p><Action disabled={busy || !approval || !eligibility.sandbox_configured || sdkReady || blocked || (!!attempt && attempt.approval_id === approval?.id && attempt.status !== 'awaiting_buyer')} reason={paymentsDisabled ? paymentDisabledReason : busy ? 'Wait for the current request.' : !eligibility.sandbox_configured ? 'Backend sandbox configuration is required.' : blocked ? 'Refresh and resolve changed checkout inputs.' : !approval ? 'Save separate exact-version checkout approval first.' : sdkReady ? 'PayPal button is ready below; opening it is an explicit payment action.' : 'Reconcile the existing attempt before continuing.'} onClick={() => void setup()}>Load PayPal sandbox button</Action><div className="paypal-button-slot" ref={container} /></div>
    </section>}
    {!receipt && <details className="help"><summary>How sandbox checkout works</summary><p>Your name is recorded for review; identity is not verified in this prototype. Approve the displayed versions first, then load the PayPal button. Payment status comes from the backend, not the approval popup.</p></details>}
    {receipt && <><div className="completed-booking-context no-print"><div><p className="eyebrow">CURRENT BOOKING WORKSPACE</p><h1>{bookingTitle || 'Booking title unavailable'}</h1></div><Status tone="success">Sandbox capture recorded</Status></div><SandboxReceipt receipt={receipt} /></>}
    {!!history.length && <details className="payment-history"><summary>Payment history · {history.length} saved attempt{history.length === 1 ? '' : 's'}</summary><table className="data-table history-table"><caption className="sr-only">Recorded payment attempts; amounts are stored values</caption><colgroup><col className="history-col-status" /><col className="history-col-amount" /><col className="history-col-details" /></colgroup><thead><tr><th scope="col">Attempt status</th><th scope="col" className="numeric">Recorded amount</th><th scope="col" className="table-actions">Details</th></tr></thead><tbody>{history.map(a => <tr key={a.id}><th scope="row" data-label="Attempt status">{labels[a.status] || a.status}</th><td className="numeric" data-label="Recorded amount">{a.currency} {a.amount}</td><td className="table-actions" data-label="Details"><TechnicalDetails label="Attempt details" data={{ ...a }} /></td></tr>)}</tbody></table></details>}

  </section>
}
