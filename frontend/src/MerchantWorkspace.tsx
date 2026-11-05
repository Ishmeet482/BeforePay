import { BlockerList, BlockerNext } from './BlockerActions'
import { categories } from './review-api'
import { row, titles } from './conditions'
import CategorySummary from './CategorySummary'
import { humanTime, money, Status } from './product-ui'
import TechnicalDetails from './TechnicalDetails'
import { merchantNext } from './workspace-state'
import type { Snapshot, Step } from './booking-state'

export function MerchantOverview({ snapshot: s, go, buyer }: { snapshot: Snapshot; go: (step: Step) => void; buyer: (step: Step) => void }) {
  const next = merchantNext(s)
  return <div className="merchant-overview"><section className={`next-action next-${next.tone}`}><p className="eyebrow">MERCHANT WORKSPACE · NEXT HANDOFF</p><h2><Status tone={next.tone}>{next.status}</Status></h2><p>{next.detail}</p><BlockerNext codes={s.receipt || s.attempts.length ? [] : s.blockers} fallback={<button className="primary" onClick={() => go(next.step)}>{next.label} →</button>} /></section>
    <section className="document-section overview-tasks">{!s.receipt && !!s.blockers.length && <details className="help"><summary>Saved blockers &amp; next actions</summary><BlockerList codes={s.blockers} /></details>}<h2>Prepare the final booking</h2><p>Same booking and saved versions as Buyer view. These prototype views do not identify or authenticate a person.</p>
      <div className="progress-row"><span>Buyer agreement</span><strong>{s.review.confirmation_current ? `Confirmed version ${s.agreement?.version}` : 'Buyer review needed'}</strong><button onClick={() => go('reference')}>Read buyer reference</button></div>
      <div className="progress-row"><span>Merchant proposal</span><strong>{s.proposal ? `Saved version ${s.proposal.version}` : 'Merchant proposal needed'}</strong><button onClick={() => go('comparison')}>{s.proposal ? 'Review / revise proposal' : 'Create final proposal'}</button></div>
      <div className="progress-row"><span>Merchant policy rules</span><strong>{s.rules.some(r => r.target.kind === 'proposal' && r.target.id === s.proposal?.id && r.approved_current) ? 'Reviewed for latest proposal' : 'Preparation / review needed'}</strong><button onClick={() => go('cancellation')}>Review merchant rules</button></div>
      <div className="progress-row"><span>Clarification replies</span><strong>{s.comparison ? "Review saved questions" : "Comparison needed first"}</strong><button onClick={() => go('clarifications')}>View questions &amp; replies</button></div>
      <div className="progress-row"><span>Buyer comparison</span><strong>{!s.review.confirmation_current ? 'Buyer confirmation needed' : !s.comparison ? 'Buyer review needed' : s.comparison.stale ? 'New buyer comparison needed' : !s.comparison.results.length || s.comparison.results.some(r => r.status !== 'matches') ? 'Resolve booking differences' : 'Saved comparison · matching'}</strong><button onClick={() => buyer('comparison')}>Open Buyer comparison</button></div>
      <div className="progress-row"><span>Recorded payment</span><strong>{s.receipt ? 'Capture recorded · sandbox' : s.attempts.length ? 'Check saved attempts' : 'No payment recorded'}</strong><button onClick={() => go('checkout')}>View payment status</button></div>
    </section></div>
}

export function BuyerReference({ snapshot: s, buyer }: { snapshot: Snapshot; buyer: (step: Step) => void }) {
  return <section className="workspace buyer-reference" aria-busy="false"><div className="toolbar"><div><h2>Buyer agreement · read-only reference</h2><p>Merchant proposals never overwrite or confirm this agreement.</p></div><button onClick={() => buyer('review')}>Open Buyer agreement review</button></div>
    <p className={`notice ${s.review.confirmation_current ? 'success' : 'attention'}`}><strong>{s.review.confirmation_current ? `Buyer-confirmed agreement · version ${s.agreement?.version}` : 'Buyer review needed'}</strong>{!s.review.confirmation_current && ' The current saved agreement is not currently confirmed. It is not an approved buyer baseline.'}</p>
    {s.agreement ? <><TechnicalDetails label="Exact agreement reference" data={{ agreement_id: s.agreement.id, fingerprint: s.agreement.fingerprint }} /><div className="reference-terms">{categories.map(category => <section className="document-section" key={category}><h3>{titles[category]}</h3><CategorySummary category={category} rows={s.agreement!.content.extraction[category].map((entry, index) => ({ ...row(entry), key: `${category}-${index}` }))} noItems={s.agreement!.content.explicit_none_categories.includes(category)} /></section>)}</div></> : <p>No saved agreement. The buyer must add evidence, generate a draft explicitly and review it.</p>}
    <p className="hint">Agreement confirmation, approval of cancellation rules and checkout approval are separate actions. Switching views performs none of them.</p>
  </section>
}

export function MerchantPayment({ snapshot: s, buyer }: { snapshot: Snapshot; buyer: (step: Step) => void }) {
  return <section className="workspace merchant-payment" aria-busy="false"><div className="toolbar"><div><h2>Recorded payment status</h2><p>Read-only sandbox capture history. No payment, retry or refund action in Merchant view.</p></div></div>
    {s.receipt ? <section className="panel"><Status tone="success">Capture recorded · sandbox</Status><h3>{money(s.receipt.amount, s.receipt.currency)}</h3><p>Recorded {humanTime(s.receipt.created_at)}</p><p>Historical capture record; not proof of current settlement.</p><button className="primary" onClick={() => buyer('checkout')}>View receipt in Buyer workspace →</button><TechnicalDetails label="Recorded receipt reference" data={{ receipt_id: s.receipt.id, context: s.receipt.context }} /></section> : <p className="notice attention"><strong>{s.attempts.length ? 'No completed capture receipt recorded.' : 'No payment recorded.'}</strong> Buyer approval or an order alone cannot establish payment. Checkout remains a separate Buyer action.</p>}
    {s.attempts.length > 0 && <div className="booking-table"><table className="data-table history-table"><caption>Saved payment attempts · recorded state only</caption><colgroup><col className="history-col-status" /><col className="history-col-amount" /><col className="history-col-details" /></colgroup><thead><tr><th scope="col">Status</th><th scope="col" className="numeric">Recorded amount</th><th scope="col" className="table-actions">References</th></tr></thead><tbody>{s.attempts.map(a => <tr key={a.id}><th scope="row" data-label="Status">{a.status.replaceAll('_', ' ')}{a.status !== 'completed' && <small>Not proof of payment</small>}</th><td className="numeric" data-label="Recorded amount">{money(a.amount, a.currency)}</td><td className="table-actions" data-label="References"><TechnicalDetails label="Attempt references" data={{ attempt_id: a.id, order_id: a.order_id }} /></td></tr>)}</tbody></table></div>}
    {!s.receipt && <button onClick={() => buyer('checkout')}>Open Buyer payment review →</button>}
  </section>
}
