import type { Category, Claim, Entry } from './review-api'
export const titles: Record<Category, string> = {
  equipment: 'Equipment', pickup: 'Pickup', return_time: 'Return', currency: 'Currency',
  amounts: 'Rental fee, deposit & total', deposit_conditions: 'Deposit conditions',
  cancellation_conditions: 'Cancellation policy', included_items: 'Included items',
}
export type Row = {
  key: string; original?: Entry; name: string; quantity: string; value: string
  timezone: string; kind: string; amount: string; currency: string; ambiguous: boolean
}
export function row(entry?: Entry): Row {
  const c = entry?.claim
  return { key: crypto.randomUUID(), original: entry, name: c?.name ?? c?.label ?? '',
    quantity: c?.quantity?.toString() ?? '', value: typeof c?.value === 'string' ? c.value : c?.value?.local_datetime ?? '',
    timezone: typeof c?.value === 'object' ? c.value.timezone ?? '' : '', kind: c?.kind ?? 'other',
    amount: c?.amount ?? '', currency: c?.currency ?? '', ambiguous: c?.ambiguous ?? false }
}
export function claim(category: Category, r: Row): Omit<Claim, 'citations'> {
  const common = { ambiguous: r.ambiguous }
  if (category === 'equipment' || category === 'included_items') {
    if (r.quantity !== '' && (!/^[1-9]\d*$/.test(r.quantity) || Number(r.quantity) > 100000)) throw new Error('Quantity must be a positive integer up to 100000, or blank if unknown.')
    return { ...common, name: r.name, quantity: r.quantity ? Number(r.quantity) : null }
  }
  if (category === 'pickup' || category === 'return_time') return { ...common, value: { local_datetime: r.value || null, timezone: r.timezone || null } }
  if (category === 'amounts') return { ...common, kind: r.kind as Claim['kind'], label: r.name, amount: r.amount, currency: r.currency || null }
  return { ...common, value: r.value }
}
export function rowsChanged(category: Category, current: Row[], saved: Entry[]): boolean {
  if (current.length !== saved.length) return true
  try {
    // Compare the same editable projection on both sides. Form-only keys and
    // provenance are not corrections; null/number values use row() normalization.
    return current.some((r, index) => JSON.stringify(claim(category, r)) !==
      JSON.stringify(claim(category, row(saved[index]))))
  } catch {
    // Invalid intermediate input is still an unsaved edit. Validation at save
    // remains authoritative; it must never make an invalid row look unchanged.
    return true
  }
}
export function blockerText(code: string): string {
  const messages: Record<string, string> = {
    rental_total_missing: 'Enter the rental fee separately from the inclusive total payable.',
    currency_mismatch: 'Currency and all amount currencies must agree.',
    return_must_follow_pickup: 'Return must be after pickup.',
    rental_time_requires_clarification: 'Resolve ambiguous dates/timezones; an explicit UTC offset may be needed.',
    unreviewed_evidence: 'Review all sources, acknowledge them below and save a review revision.',
    evidence_changed_requires_review: 'Evidence changed. Review all current sources and save a new revision.',
    newer_ai_draft_requires_review: 'A newer saved AI draft requires review. Open it explicitly below.',
    agreement_missing: 'Open a saved draft to start review.',
    agreement_changed: 'The agreement changed. Review its latest version.',
    merchant_booking_changed: 'The merchant booking changed. Compare its latest version.',
    confirmation_no_longer_current: 'Confirm the latest agreement before continuing.',
    current_confirmation_required: 'Review and confirm the latest agreement.',
    checkout_blocked: 'Checkout cannot continue until the issues below are resolved.',
    checkout_context_stale: 'Checkout terms changed. Refresh and approve them again.',
    checkout_approval_stale: 'Your checkout approval is out of date. Refresh and review the latest terms.',
    stale_agreement: 'A newer agreement is available. Refresh before saving or confirming.',
    stale_merchant_booking: 'The merchant booking changed. Refresh before saving or comparing.',
    stale_cancellation_rule: 'Cancellation rules changed. Refresh and review them again.',
    merchant_booking_required: 'Save a merchant booking before checkout.',
    current_all_matching_comparison_required: 'Compare the latest booking with your confirmed agreement.',
    stale_clarification_reply_context: 'This question or proposal changed. Refresh current questions before replying. No response was saved.',
    clarification_comparison_stale: 'The saved comparison or its inputs changed. Refresh and compare current versions before suggesting a question.',
    stale_comparison_fingerprint: 'The saved comparison fingerprint changed. Refresh the current comparison.',
    clarification_inputs_changed_during_generation: 'Inputs changed while generating. No clarification was saved. Refresh the comparison.',
    comparison_terms_do_not_match_versions: 'Saved comparison terms do not match their versions. Refresh and compare again.',
    comparison_stale: 'Compare the latest versions again.',
    comparison_has_differences_or_clarification: 'Resolve booking differences and unclear terms before checkout.',
    deterministic_terms_not_matching: 'Equipment, dates or amounts differ. Review the comparison.',
    inconsistent_deposit_cancellation_policies: 'Deposit and cancellation terms conflict. Resolve them before checkout.',
    reviewed_cancellation_refunds_differ: 'The reviewed refund rules differ. Resolve them before checkout.',
    agreement_reviewed_cancellation_rules_required: 'Review and confirm cancellation rules for the agreement.',
    proposal_reviewed_cancellation_rules_required: 'Review and confirm cancellation rules for the merchant booking.',
    agreement_cancellation_rules_unapproved_stale_or_inconsistent: 'Review the latest agreement cancellation rules and resolve any conflicts.',
    proposal_cancellation_rules_unapproved_stale_or_inconsistent: 'Review the latest merchant cancellation rules and resolve any conflicts.',
    sandbox_payment_already_completed: 'This booking already has a completed sandbox payment.',
    explicit_positive_USD_total_payable_required: 'Enter a positive total payable in USD before checkout.',
    source_version_or_confirmation_stale: 'The source version changed or needs confirmation. Review the latest version.',
    source_fingerprint_mismatch: 'The source changed. Refresh before reviewing its rules.',
    newer_rule_version_requires_review: 'Review and confirm the latest rule version.',
    reviewed_current_rule_approval_required: 'Review and confirm the current cancellation rules before previewing.',
    reviewer_flagged_incomplete_or_conflicting_policy: 'Resolve the missing or conflicting policy terms you flagged.',
    deposit_cancellation_policy_conflict: 'The deposit policy conflicts with promised cancellation refunds.',
    deposit_clause_not_supported_by_source_version: 'Copy the supporting deposit clause exactly from this source.',
    explicit_rental_deposit_and_total_required: 'Record separate rental fee, deposit and total payable amounts.',
    inclusive_total_does_not_equal_rental_plus_deposit: 'Total payable must equal the stated rental fee plus deposit for this preview.',
    additional_charges_require_clarification: 'This preview does not support additional charges. Clarify the amounts first.',
    duplicate_amount_kind: 'Resolve repeated amount types before previewing.',
    explicit_unique_pickup_required: 'Record one complete pickup time.',
    pickup_timezone_or_datetime_unresolved: 'Clarify the pickup date, time and timezone.',
    only_pre_pickup_cancellation_supported: 'Choose a cancellation time before pickup.',
    explicit_cancellation_datetime_and_timezone_required: 'Enter the cancellation date, time and timezone.',
    cancellation_timezone_requires_clarification: 'This cancellation time is ambiguous. Enter an explicit UTC offset.',
    cutoff_hours_not_explicit_in_cited_clauses: 'Check that the cited clause states this cutoff in hours.',
    unsupported_cutoff_hours: 'Enter a supported positive cutoff in hours.',
    explicit_unique_USD_currency_required: 'This preview requires one explicit USD currency with matching component amounts.',
    distinct_rule_versions_required: 'Select distinct saved rule versions for the comparison.',
    side_by_side_requires_agreement_and_proposal: 'Side-by-side preview needs one buyer agreement rule version and one merchant proposal rule version.',
    unsupported_or_ambiguous_amounts_USD_cents_required: 'Use clear USD amounts with no fractions of a cent.',
    typed_values_equal: 'Values match.', typed_values_differ: 'Values differ.',
    identical_policy_text: 'Policy text matches.', policy_meaning_comparison: 'Policy meaning checked.',
    missing_or_ambiguous_terms: 'Missing or unclear terms need review.',
    missing_amount_kind: 'One version is missing a stated amount type.',
    unresolved_policy: 'Resolve the flagged or conflicting policy terms.',
    explicitly_no_included_items: 'Both versions explicitly include no additional items.',
    included_items_differ: 'Included items differ.',
    paypal_timeout: 'PayPal did not respond in time. Check payment status before retrying.',
    paypal_http_error: 'PayPal could not complete the request. Check payment status before retrying.',
    paypal_capture_pending: 'PayPal is still processing the capture. Check its status later.',
    paypal_capture_declined: 'PayPal declined the capture. No completed payment was recorded.',
    paypal_buyer_approval_required: 'Approve this order in PayPal before capture can continue.',
    merchant_policy_consistency_requires_clarification: 'Saved merchant deposit/cancellation findings need clarification. Revise the proposal and recheck policy consistency.',
    policy_consistency_proposal_stale: 'The saved merchant proposal changed. Refresh policy checks before checking the new version.',
    buyer_cancelled: 'Buyer checkout was cancelled.',
    capture_request_prepared: 'Capture status is not yet confirmed. Check PayPal status.',
    reconcile_or_manual_review_required: 'Check PayPal status. An uncertain capture must not be replaced with a new payment.',
    manual_reconciliation_required: 'Manual payment review is required before another attempt.',
    capture_may_have_occurred_reconcile_required: 'A capture may have occurred. Check PayPal status instead of cancelling.',
    existing_payment_attempt_requires_resolution: 'Resolve the existing checkout attempt before starting another.',
    payment_attempt_not_capturable: 'This checkout attempt cannot be captured. Review its payment status.',
    paypal_sandbox_not_configured: 'Sandbox checkout is not configured. Check backend settings.',

  }
  if (messages[code]) return messages[code]
  for (const cat of Object.keys(titles) as Category[]) {
    if (code === `${cat}_missing`) return `${titles[cat]}: required information is missing.`
    if (code === `${cat}_unresolved`) return `${titles[cat]}: resolve conflicts, unknown values or flagged uncertainty.`
  }
  for (const band of ['early', 'late']) {
    const when = band === 'early' ? 'earlier' : 'later'
    if (code === `${band}_clause_not_supported_by_source_version`) return `Copy the supporting ${when} cancellation clause exactly from the source.`
    if (code === `${band}_deposit_refund_conflicts_with_nonrefundable_policy`) return `The ${when} refund returns a deposit described as non-refundable.`
    if (code === `${band}_refund_amount_or_precision_unsupported`) return `Check the ${when} refund amounts, percentages and cent precision.`
    if (code === `${band}_full_refund_clause_conflicts_with_split`) return `The ${when} clause promises a full refund, but the component refunds do not match.`
    if (code === `${band}_no_refund_clause_conflicts_with_split`) return `The ${when} clause says no refund, but the rules return money.`
  }
  if (code.startsWith('cutoff_boundary_conflicts_with_')) return 'The cutoff boundary does not match the cited clause. Check which band includes it.'
  if (code.endsWith('_missing_or_conflicting')) return 'Review the missing or conflicting policy clauses.'
  return code.replaceAll('_', ' ')
}

export function friendlyError(message: string): string {
  const parts = message.split(': ')
  const isCode = (part: string) => /^[a-zA-Z][a-zA-Z_]+$/.test(part) && part.includes('_')
  return parts.some(isCode) ? parts.map(part => isCode(part) ? blockerText(part) : part).join(' ') : message
}
export function relevant(category: Category, code: string): boolean {
  return code.startsWith(`${category}_`) || (category === 'amounts' && ['rental_total_missing', 'currency_mismatch'].includes(code)) ||
    (category === 'currency' && code === 'currency_mismatch') ||
    (['pickup', 'return_time'].includes(category) && ['return_must_follow_pickup', 'rental_time_requires_clarification'].includes(code))
}
