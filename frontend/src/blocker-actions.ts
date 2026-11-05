import type { Snapshot, Step } from './booking-state'
import type { Workspace } from './workspace-state'
import { blockerText } from './conditions'

export type RuleKind = 'agreement' | 'proposal'
export type Destination = { workspace: Workspace; step: Step; selector?: string; kind?: RuleKind }
export type BlockerScope = { kind?: RuleKind; sourceVersion?: number; ruleVersion?: number }
type Definition = { label: string; destination: Destination; affected: 'agreement' | 'proposal' | 'comparison' | 'rules' | 'payment' | 'calculator'; priority: number }
const definitions: Record<string, Definition> = {}
function register(codes: string[], label: string, destination: Destination, affected: Definition['affected'], priority = 50) {
  for (const code of codes) definitions[code] = { label, destination, affected, priority }
}
register(['merchant_policy_consistency_requires_clarification'], 'Open merchant policy findings', { workspace: 'merchant', step: 'cancellation', selector: '.policy-consistency' }, 'proposal', 10)
register(['comparison_stale', 'current_all_matching_comparison_required', 'merchant_booking_changed', 'stale_comparison_fingerprint', 'clarification_comparison_stale', 'comparison_superseded'], 'Review saved comparison', { workspace: 'buyer', step: 'comparison', selector: '.buyer-comparison' }, 'comparison', 20)
register(['comparison_has_differences_or_clarification', 'deterministic_terms_not_matching'], 'Review booking differences', { workspace: 'buyer', step: 'comparison', selector: '.buyer-comparison' }, 'comparison', 25)
register(['merchant_booking_required', 'explicit_positive_USD_total_payable_required', 'inconsistent_deposit_cancellation_policies'], 'Review merchant proposal', { workspace: 'merchant', step: 'comparison', selector: '.merchant-editor > summary' }, 'proposal', 15)
for (const kind of ['agreement', 'proposal'] as const) register([`${kind}_reviewed_cancellation_rules_required`, `${kind}_cancellation_rules_unapproved_stale_or_inconsistent`], kind === 'agreement' ? 'Review buyer agreement rules' : 'Review merchant policy rules', { workspace: kind === 'agreement' ? 'buyer' : 'merchant', step: 'cancellation', kind, selector: '.rule-workbench > summary' }, 'rules', kind === 'agreement' ? 30 : 31)
register(['reviewed_cancellation_refunds_differ'], 'Compare reviewed refund rules', { workspace: 'buyer', step: 'cancellation', selector: '.policy-selection' }, 'rules', 35)
register(['agreement_missing', 'agreement_changed', 'stale_agreement', 'confirmation_no_longer_current', 'current_confirmation_required', 'unreviewed_evidence', 'evidence_changed_requires_review', 'newer_ai_draft_requires_review', 'rental_total_missing', 'currency_mismatch', 'return_must_follow_pickup', 'rental_time_requires_clarification'], 'Review buyer agreement', { workspace: 'buyer', step: 'review' }, 'agreement', 5)
for (const category of ['equipment', 'included_items', 'pickup', 'return_time', 'currency', 'amounts', 'deposit_conditions', 'cancellation_conditions']) register([`${category}_missing`, `${category}_unresolved`], 'Review buyer agreement', { workspace: 'buyer', step: 'review' }, 'agreement', 5)
register(['sandbox_payment_already_completed'], 'View receipt', { workspace: 'buyer', step: 'checkout' }, 'payment')
register(['source_version_or_confirmation_stale', 'source_fingerprint_mismatch', 'newer_rule_version_requires_review', 'reviewed_current_rule_approval_required', 'reviewer_flagged_incomplete_or_conflicting_policy', 'deposit_cancellation_policy_conflict', 'deposit_clause_not_supported_by_source_version', 'explicit_unique_USD_currency_required', 'unsupported_or_ambiguous_amounts_USD_cents_required', 'duplicate_amount_kind', 'additional_charges_require_clarification', 'explicit_rental_deposit_and_total_required', 'inclusive_total_does_not_equal_rental_plus_deposit', 'unsupported_cutoff_hours', 'cutoff_hours_not_explicit_in_cited_clauses', 'cutoff_boundary_conflicts_with_at_least_clause', 'cutoff_boundary_conflicts_with_more_than_clause', 'cutoff_boundary_conflicts_with_less_than_clause', 'deposit_conditions_missing_or_conflicting', 'cancellation_conditions_missing_or_conflicting', 'explicit_unique_pickup_required', 'pickup_timezone_or_datetime_unresolved', ...['early', 'late'].flatMap(band => [`${band}_clause_not_supported_by_source_version`, `${band}_deposit_refund_conflicts_with_nonrefundable_policy`, `${band}_full_refund_clause_conflicts_with_split`, `${band}_no_refund_clause_conflicts_with_split`, `${band}_refund_amount_or_precision_unsupported`])], 'Review source and rule requirements', { workspace: 'buyer', step: 'cancellation', selector: '.rule-workbench > summary' }, 'rules')
register(['only_pre_pickup_cancellation_supported', 'explicit_cancellation_datetime_and_timezone_required', 'cancellation_timezone_requires_clarification'], 'Review cancellation instant', { workspace: 'buyer', step: 'cancellation', selector: '.cancellation-start input' }, 'calculator')
register(['distinct_rule_versions_required', 'side_by_side_requires_agreement_and_proposal'], 'Review side-by-side policy selection', { workspace: 'buyer', step: 'cancellation', selector: '.policy-selection' }, 'calculator')

/** Exact backend codes only. Unknown codes never acquire a guessed destination. */
export function blockerAction(code: string, workspace: Workspace, snapshot?: Snapshot | null, scope: BlockerScope = {}) {
  const def = definitions[code]
  if (!def) return { code, explanation: `Unrecognised blocker: ${code}. Refresh saved state; no automatic destination is available.`, affected: 'Affected saved version not supplied.', priority: 100, label: null, destination: null }
  const destination = { ...def.destination }
  const ruleKind = code.startsWith('proposal_') ? 'proposal' : code.startsWith('agreement_') ? 'agreement' : scope.kind
  if (def.affected === 'rules' && code !== 'reviewed_cancellation_refunds_differ') {
    if (!ruleKind) return { code, explanation: blockerText(code), affected: 'Rule source not supplied. Review the source-specific blocker before choosing a rule version.', priority: def.priority, label: null, destination: null }
    destination.kind = ruleKind; destination.workspace = ruleKind === 'agreement' ? 'buyer' : 'merchant'
  }
  // Findings may be read in either view; this does not grant merchant editing rights.
  if (code === 'merchant_policy_consistency_requires_clarification') destination.workspace = workspace
  const sourceKind = def.affected === 'agreement' ? 'agreement' : def.affected === 'proposal' ? 'proposal' : ruleKind
  const source = sourceKind === 'agreement' ? snapshot?.agreement : sourceKind === 'proposal' ? snapshot?.proposal : null
  const version = sourceKind === scope.kind ? scope.sourceVersion ?? source?.version : source?.version
  const ruleVersion = scope.ruleVersion ?? snapshot?.rules.filter(r => r.target.kind === sourceKind && r.target.id === source?.id).sort((a, b) => b.version - a.version)[0]?.version
  const sourceLabel = sourceKind === 'agreement' ? 'Buyer agreement' : 'Merchant proposal'
  const affected = def.affected === 'comparison' ? `Saved comparison · ${snapshot?.comparison?.stale ? 'outdated' : 'refresh to verify context'}; buyer agreement ${snapshot?.agreement?.version ?? 'not available'}, merchant proposal ${snapshot?.proposal?.version ?? 'not available'}.`
    : def.affected === 'payment' ? 'Existing saved payment / receipt.' : def.affected === 'calculator' ? (destination.selector === '.policy-selection' ? 'Selected saved agreement and merchant rule versions.' : 'Entered cancellation instant; no saved terms are changed.')
    : def.affected === 'rules' && code === 'reviewed_cancellation_refunds_differ' ? 'Both saved agreement and merchant rule versions.'
    : `${sourceLabel} ${version == null ? 'version not available' : `version ${version}`}${def.affected !== 'rules' ? '' : ruleVersion == null ? ' · no saved rule version available' : ` · rule version ${ruleVersion}`}.`
  return { code, explanation: blockerText(code), affected, priority: def.priority, label: `${destination.workspace !== workspace ? `Switch to ${destination.workspace === 'buyer' ? 'Buyer' : 'Merchant'} demo view · ` : ''}${def.label}`, destination }
}
