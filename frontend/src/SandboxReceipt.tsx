import Brand from './Brand'
import { useRef, useState } from 'react'
import TechnicalDetails from './TechnicalDetails'
import { humanTime, money } from './product-ui'

export type CaptureContext = {
  environment: 'sandbox'; agreement_id: string; agreement_version: number; agreement_fingerprint: string
  proposal_id: string; proposal_version: number; proposal_fingerprint: string
  comparison_id: string; comparison_fingerprint: string; amount: string; currency: string
  confirmation_id?: string; cancellation_rules?: { id: string; fingerprint: string; approval_id: string }[]
}
export type CaptureReceipt = {
  id: string; booking_id?: string; attempt_id?: string; approval_id?: string
  context: CaptureContext; amount: string; currency: string; order_id: string; capture_id: string; created_at: string
}
export function CopyReference({ label, value }: { label: string; value?: string }) {
  const [state, setState] = useState('')
  const trigger = useRef<HTMLButtonElement>(null)
  async function copy() {
    if (!value) return
    try {
      try { await navigator.clipboard.writeText(value) }
      catch {
        // Older browsers / denied Clipboard API: preserve a user-triggered fallback.
        const field = document.createElement('textarea')
        field.value = value; field.className = 'copy-fallback'; field.readOnly = true
        document.body.append(field); field.select()
        let copied = false
        try { copied = document.execCommand('copy') } finally { field.remove(); trigger.current?.focus() }
        if (!copied) throw new Error('Clipboard unavailable')
      }
      setState('Copied')
    } catch { setState('Copy unavailable. Select and copy the reference manually.') }
  }
  return <div className="receipt-reference"><dt>{label}</dt><dd><code>{value || 'Not stored'}</code>{value && <button type="button" ref={trigger} className="copy-reference no-print" aria-label={`Copy ${label.toLowerCase()}`} onClick={() => void copy()}>Copy</button>}</dd><span className="copy-status no-print" role="status">{state}</span></div>
}
export default function SandboxReceipt({ receipt: r }: { receipt: CaptureReceipt }) {
  const [printError, setPrintError] = useState('')
  function print() {
    setPrintError('')
    try { window.print() } catch { setPrintError('Print could not open. Use your browser’s Print command.') }
  }
  return <article id="payment-receipt" className="completed-receipt" aria-labelledby="receipt-heading">
    <header className="receipt-header"><div><span className="receipt-brand"><Brand /></span><p>Sandbox payment receipt</p></div><div className="receipt-seal"><strong>Capture completed</strong><span>Test funds only</span></div></header>
    <div className="receipt-heading"><div><h2 id="receipt-heading">Payment recorded</h2><p className="receipt-booking">Sandbox capture record</p><p className="receipt-label-note">Historical record of the exact approved versions</p></div><button className="no-print" type="button" onClick={print}>Print receipt</button></div>
    {printError && <p className="field-error no-print" role="alert">{printError}</p>}
    <section className="receipt-amount"><span>Captured amount</span><strong>{money(r.amount, r.currency)}</strong><p>Recorded {humanTime(r.created_at)}</p></section>
    <p className="receipt-snapshot-note">Itemised amounts were not stored with this capture. Only the recorded total is shown.</p>
    <div className="receipt-columns"><section><h3>Receipt & payment references</h3><dl><CopyReference label="Receipt reference" value={r.id} /><CopyReference label="PayPal order reference" value={r.order_id} /><CopyReference label="PayPal capture reference" value={r.capture_id} /></dl></section><section><h3>Exact approved versions</h3><dl className="approved-references"><CopyReference label={`Agreement version ${r.context.agreement_version}`} value={r.context.agreement_id} /><CopyReference label={`Merchant version ${r.context.proposal_version}`} value={r.context.proposal_id} /><CopyReference label="Saved comparison" value={r.context.comparison_id} /><CopyReference label="Checkout approval" value={r.approval_id} />{r.context.confirmation_id && <CopyReference label="Agreement confirmation" value={r.context.confirmation_id} />}</dl></section></div>
    {!!r.context.cancellation_rules?.length && <section className="receipt-rules"><h3>Reviewed cancellation rule references</h3><dl>{r.context.cancellation_rules.map((rule, i) => <div key={rule.id}><dt>Rule {i + 1}</dt><dd><code>{rule.id}</code><span>Approval <code>{rule.approval_id}</code></span></dd></div>)}</dl></section>}
    <div className="receipt-audit no-print"><TechnicalDetails label="Captured fingerprints & audit references" data={{ receipt_id: r.id, booking_id: r.booking_id, attempt_id: r.attempt_id, approval_id: r.approval_id, recorded_at: r.created_at, context: r.context }} /></div>
    <footer className="receipt-footer"><strong>Issued by BeforePay for a PayPal sandbox capture.</strong><p>This app-issued receipt is a historical capture record, not a PayPal-issued document or proof of current settlement. No real funds moved. Later changes do not rewrite the recorded amount or approved references.</p></footer>
  </article>
}
