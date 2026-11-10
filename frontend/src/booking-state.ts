import type { Tone } from './product-ui'
import { claim, corroboratedRows, row } from './conditions'
import { request, type Agreement, type Claim, type Category, type ReviewState } from './review-api'
export type Step = 'clarifications' | 'reference' | 'overview' | 'sources' | 'review' | 'comparison' | 'cancellation' | 'checkout'
export type ProposalSummary = { id: string; version: number; fingerprint: string; content: Record<string, Claim[]> }
export type ComparisonSummary = { id: string; stale: boolean; results: { category: string; status: string }[] }
export type RuleSummary = { target: { kind: string; id: string }; approved_current: boolean; blockers: string[]; version: number }
export type AttemptSummary = { id: string; status: string; order_id: string | null; amount: string; currency: string }
export type ReceiptSummary = { id: string; amount: string; currency: string; created_at: string; context?: { agreement_id: string; agreement_version: number; proposal_id: string; proposal_version: number } }
export type Snapshot = { review: ReviewState; agreement: Agreement | null; proposal: ProposalSummary | null; comparison: ComparisonSummary | null; rules: RuleSummary[]; attempts: AttemptSummary[]; receipt: ReceiptSummary | null; eligible: boolean; blockers: string[]; sandboxConfigured: boolean }
export async function loadSnapshot(id: string, signal?: AbortSignal): Promise<Snapshot> {
  const saved = await request<Omit<Snapshot, 'sandboxConfigured'> & { sandbox_configured: boolean }>(`/bookings/${id}/saved-state`, { signal })
  if (!saved?.review || !Array.isArray(saved.rules) || !Array.isArray(saved.attempts) || !Array.isArray(saved.blockers) || typeof saved.eligible !== 'boolean') throw new Error('Saved booking state response is incomplete. Check that the updated backend is deployed; no empty or approved state was assumed.')
  return { ...saved, sandboxConfigured: saved.sandbox_configured }
}
export function nextStep(s: Snapshot): { step: Step; label: string; status: string; detail: string; tone: Tone } {
  if (s.receipt) return { step: 'checkout', label: 'View receipt', status: 'Paid · sandbox', tone: 'success', detail: 'Completed capture recorded. Receipt preserves the versions paid for.' }
  const active = s.attempts.find(a => ['creating', 'create_uncertain', 'capture_uncertain', 'pending', 'awaiting_buyer'].includes(a.status))
  if (active) return { step: 'checkout', label: 'Review payment status', tone: 'attention', status: active.status === 'awaiting_buyer' ? 'Awaiting buyer approval' : 'Payment outcome pending', detail: 'Check the saved attempt before any new payment. Pending is not paid.' }
  if (!s.review.latest_draft_id && !s.agreement) return { step: 'sources', label: 'Add quotation & messages', status: 'Sources needed', tone: 'neutral', detail: 'Start with the quotation and supporting messages. AI generation is a separate action.' }
  if (!s.review.confirmation_current) return { step: 'review', label: s.agreement ? 'Review agreement' : 'Review extracted terms', status: 'Awaiting review', tone: 'attention', detail: 'Review evidence and confirm the exact agreement version before comparison.' }
  if (!s.proposal) return { step: 'comparison', label: 'Open merchant handoff', status: 'Merchant proposal needed', tone: 'attention', detail: 'Switch to Merchant prototype view to prepare the final booking, then return for buyer comparison.' }
  if (!s.comparison || s.comparison.stale) return { step: 'comparison', label: 'Compare merchant booking', tone: 'attention', status: s.comparison?.stale ? 'Comparison out of date' : 'Comparison needed', detail: 'Explicitly compare the saved versions. No automatic policy judgments.' }
  if (s.comparison.results.some(r => r.status !== 'matches') || !s.comparison.results.length) return { step: 'comparison', label: s.comparison.results.some(r => r.category === 'deposit_conditions' && r.status === 'differs') ? 'Resolve deposit change' : 'Review differences', status: 'Terms need attention', tone: 'blocked', detail: 'An unchanged total does not mean the agreement is unchanged.' }
  const approved = (kind: string, id?: string) => s.rules.some(r => r.target.kind === kind && r.target.id === id && r.approved_current)
  if (!approved('agreement', s.agreement?.id) || !approved('proposal', s.proposal.id)) return { step: 'cancellation', label: 'Review cancellation rules', status: 'Policy review needed', tone: 'attention', detail: 'Both versions need complete, current, explicitly approved cancellation rules.' }
  if (!s.eligible) return { step: 'checkout', label: 'Review checkout blockers', status: 'Checkout blocked', tone: 'blocked', detail: 'Backend checks still require attention before checkout approval.' }
  return { step: 'checkout', label: 'Review & approve checkout', status: 'Ready for checkout', tone: 'success', detail: 'Review the inclusive total, then approve checkout separately from PayPal buyer approval.' }
}
export function snapshotClaims(s?: Snapshot): Record<string, Claim[]> | null {
  if (!s) return null
  if (s.agreement) return Object.fromEntries(Object.entries(s.agreement.content.extraction).map(([k, v]) => [k, corroboratedRows(k as Category, v.map(row), true).map(r => ({ ...claim(k as Category, r), citations: r.original?.claim.citations ?? [] }))]))
  return s.proposal?.content ?? null
}

export function stageState(s: Snapshot | null, step: Step): { label: string; tone: Tone } {
  if (!s) return { label: 'Checking saved state', tone: 'neutral' }
  if (step === 'clarifications') return { label: s.comparison ? 'Saved questions & responses' : 'Comparison needed', tone: 'neutral' }
  if (step === 'reference') return { label: s.review.confirmation_current ? 'Buyer confirmed · read-only' : 'Buyer review needed', tone: s.review.confirmation_current ? 'success' : 'attention' }
  if (step === 'overview') return { label: 'Rental & next action', tone: 'neutral' }
  if (step === 'sources') return { label: s.review.latest_draft_id ? 'Draft saved' : 'Evidence needed', tone: s.review.latest_draft_id ? 'success' : 'neutral' }
  if (step === 'review') return { label: s.review.confirmation_current ? 'Buyer confirmed' : 'Review required', tone: s.review.confirmation_current ? 'success' : 'attention' }
  if (step === 'comparison') {
    if (!s.review.confirmation_current) return { label: 'Buyer confirmation needed', tone: 'attention' }
    if (!s.proposal) return { label: 'Merchant booking needed', tone: 'attention' }
    if (!s.comparison) return { label: 'Comparison needed', tone: 'attention' }
    if (s.comparison.stale) return { label: 'Out of date', tone: 'attention' }
    if (!s.comparison.results.length || s.comparison.results.some(r => r.status !== 'matches')) return { label: 'Terms need resolution', tone: 'blocked' }
    return { label: 'Compared · matching', tone: 'success' }
  }
  if (step === 'cancellation') {
    const approved = ['agreement','proposal'].every(kind => s.rules.some(r => r.target.kind === kind && r.target.id === (kind === 'agreement' ? s.agreement?.id : s.proposal?.id) && r.approved_current))
    return { label: approved ? 'Both policies confirmed' : 'Rule approval needed', tone: approved ? 'success' : 'attention' }
  }
  if (s.receipt) return { label: 'Capture recorded', tone: 'success' }
  if (s.attempts.some(a => ['creating','create_uncertain','capture_uncertain','pending','awaiting_buyer'].includes(a.status))) return { label: 'Payment not confirmed', tone: 'attention' }
  return { label: s.eligible ? 'Eligible for approval' : 'Not ready to pay', tone: s.eligible ? 'success' : 'blocked' }
}
