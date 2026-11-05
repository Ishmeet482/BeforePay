import { nextStep, type Snapshot, type Step } from './booking-state'

export type Workspace = 'buyer' | 'merchant'
export function workspaceRoute(workspace: Workspace, id = '') {
  return `${workspace === 'merchant' ? 'merchant/' : ''}bookings${id ? `/${id}` : ''}`
}
export function parseWorkspaceRoute(hash: string) {
  const workspace: Workspace = hash.startsWith('merchant/') ? 'merchant' : 'buyer'
  const route = workspace === 'merchant' ? hash.slice('merchant/'.length) : hash
  return { workspace, route, id: route.match(/^bookings\/([^/]+)$/)?.[1] }
}
export function merchantNext(s: Snapshot): ReturnType<typeof nextStep> {
  if (s.receipt) return { step: 'checkout', status: 'Capture recorded · sandbox', label: 'View recorded payment', detail: 'A historical capture is recorded. The buyer receipt preserves the exact paid versions.', tone: 'success' }
  if (s.attempts.some(a => ['creating', 'create_uncertain', 'capture_uncertain', 'pending', 'awaiting_buyer'].includes(a.status))) return { step: 'checkout', status: 'Payment not confirmed', label: 'View recorded payment status', detail: 'The buyer must check the existing attempt before any retry. Pending or buyer approval alone is not paid.', tone: 'attention' }
  if (!s.review.confirmation_current) return { step: 'reference', status: 'Buyer review needed', label: 'Review buyer handoff', detail: 'The buyer must review evidence and explicitly confirm the current agreement. A merchant proposal can be prepared independently.', tone: 'attention' }
  if (!s.proposal) return { step: 'comparison', status: 'Merchant proposal needed', label: 'Prepare final booking proposal', detail: 'Save a separate merchant version. The buyer-confirmed agreement remains unchanged.', tone: 'attention' }
  if (s.comparison && !s.comparison.stale && (!s.comparison.results.length || s.comparison.results.some(r => r.status !== 'matches'))) return { step: 'comparison', status: 'Resolve booking differences', label: 'Review and revise proposal', detail: 'The saved comparison reports differences or clarification. Revisions require a new merchant version and a new buyer comparison.', tone: 'blocked' }
  if (!s.rules.some(r => r.target.kind === 'proposal' && r.target.id === s.proposal?.id && r.approved_current)) return { step: 'cancellation', status: 'Merchant policy review needed', label: 'Review merchant policy rules', detail: 'Prepare and explicitly approve rules for the exact latest merchant proposal. This is separate from buyer agreement confirmation.', tone: 'attention' }
  return { step: 'reference', status: 'Buyer review needed', label: 'View buyer handoff', detail: !s.comparison || s.comparison.stale ? 'The buyer must explicitly compare the latest saved versions. No comparison runs on workspace switching.' : 'Merchant proposal and policy rules are saved. The buyer still reviews agreement rules, checkout readiness and explicit payment approval.', tone: 'attention' }
}
export function workspaceNext(s: Snapshot, workspace: Workspace) {
  return workspace === 'merchant' ? merchantNext(s) : nextStep(s)
}
