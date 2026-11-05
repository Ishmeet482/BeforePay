# Explicit versus unresolved commitments — offline prompt refinement

## Preserved cmp-08 result

The [six-case pilot](policy-pilot-v2-2026-11-04.md) used comparison prompt
`rental-policy-comparison-v1`. Its preserved cmp-08 response was:

- Buyer: “The deposit is returned after undamaged equipment is returned.”
- Merchant: “Deposit refundability will be decided later.”
- Actual: `differs`; frozen expectation: `needs_clarification`.
- Both quotations passed the production literal-support validator.

The schema has no explanation field. We **cannot know the model's actual reasoning**
from that response. A plausible explanation is competing instructions in v1:
“An added, removed or changed obligation differs” and “If meaning is ambiguous or
not established, needs_clarification.” Replacing a refund promise with an undecided
outcome changes certainty, but v1 did not explicitly prioritise the uncertainty
classification for that situation. This explanation is an inference from the
prompt and recorded output, not an additional model response.

## Checkout consequence

`backend/app/payments/eligibility.py` requires every comparison category to be
`matches`. Either `differs` or `needs_clarification` adds
`comparison_has_differences_or_clarification` and returns no eligible checkout
context. Thus the recorded classification is a frozen-label mismatch, **not a false
match or payment permission**. The synthetic pilot itself did not create a saved
booking comparison or exercise checkout. An existing receipt is not rewritten.

## Prompt v2 distinction

Only the comparison system instruction and its metadata version changed, to
`rental-policy-comparison-v2`. Schema, validators, provider transport/model settings,
retry limit, server guards and approval steps are unchanged.

| Relevant commitment | Intended status | Reason |
| --- | --- | --- |
| Refund after undamaged return versus never refund under those same conditions | `differs` | Explicit opposing commitments |
| Definite refund promise versus “will be decided later” | `needs_clarification` | No definite merchant outcome |
| Refund possible at sole discretion without decision criteria | `needs_clarification` | Scope/criteria remain unresolved |
| Explicitly bounded right to retain a named fee versus full deposit return | `differs` | A defined change, even if expressed with “may” |
| Permission to request a refund, followed by an explicit obligation to refund under stated conditions | Can be `matches` if equivalent | “May request” does not erase the definite refund promise |
| Same explicit merchant-cancellation exception with equivalent wording | `matches` | Same established outcome and conditions |

V2 gives unresolved outcome, qualifying conditions or scope priority over `differs`
for that unresolved commitment. It explicitly says such a replacement must never
be called `matches`, and forbids converting discretion into either a refund promise
or a promise never to refund. It avoids keyword classification: “may” alone is not
uncertainty. All clauses, scopes and exceptions must be considered together; embedded
instructions remain untrusted data. Exact side-bound quotation checks still apply.

The schema still permits only one status per policy category, not simultaneous
“changed obligation” and “uncertain outcome” flags. Uncertainty priority is a reporting
convention; it does not assert that an unresolved replacement has no material effect.
Exact saved wording remains available for review. New comparison results require
the existing explicit action; no saved comparisons are reclassified automatically.
The separate consistency/rule-proposal/clarification adapters retain their own
overridden prompts and versions despite sharing the transport base class.

## Offline verification

- Seven new mocked SDK response cases cover explicit conflict, deferred decision,
  undefined discretion, equivalent exception, bounded optional fee, permission to
  request a guaranteed refund, and an instruction embedded in undecided wording.
  They verify the actual v2 system instruction, unchanged input text, metadata,
  one-attempt request, structured decoding and production quotation validation.
- Three isolated tests call the **actual checkout eligibility function**, mocking
  all other prerequisites ready: `matches` can pass that isolated guard; both
  nonmatching statuses return the comparison blocker and no eligible context.
  They use in-memory mocks, not database records or payment-provider calls.
- New tests plus frozen evaluation and pilot-safety regressions: **57 passed**.
  Focused existing comparison adapter error/transport checks: **5 passed**.
  Existing consistency parse/mock-transport checks: **2 passed**.
  Total: **64 distinct focused offline checks**, six existing dependency warnings.
  Changed-file Ruff lint/format checks passed. No database fixture or migration ran.
- Initial eligibility-test fixtures omitted required amount labels/ambiguity flags;
  corrected fixtures to the existing schema without changing application guards.

Commands, from `backend/`:

```sh
uv run --frozen --offline pytest -q tests/test_policy_commitment_distinctions.py tests/test_policy_evaluation.py tests/test_policy_pilot.py
uv run --frozen --offline pytest -q tests/test_booking_comparisons.py -k 'policy_provider_failures_have_no_fallback or policy_provider_request_and_invalid_output or policy_missing_credentials_clear_error'
uv run --frozen --offline pytest -q tests/test_policy_consistency.py -k 'prompt_and_structured_parse or adapter_uses_existing_offline_transport_seam'
uv run --frozen --offline ruff check app/comparisons/provider.py tests/test_policy_commitment_distinctions.py
uv run --frozen --offline ruff format --check app/comparisons/provider.py tests/test_policy_commitment_distinctions.py
```

The checks used a temporary uv cache and blocked/faked provider clients. Mocked
responses are arranged expectations: **they do not prove v2 will classify natural
language correctly**, resist real prompt injection or improve cmp-08. No v2 live
inference occurred. The frozen dataset informed this refinement, so it is now
development feedback rather than an independent held-out measure of v2 quality.
Any future live comparison must be separately authorised, record prompt v2 and be
reported separately from v1; broader claims need unseen cases.

Frozen v2 file SHA-256 remains
`63cb5bc9f010ee942aea4f17dc22c08541251b43cd545ea18fae86ebd29d2777`.
Pilot journal SHA-256 remains
`fb7c913e6b2806f150dab01ef9c1f0b99b0c4c28b318a5f69a2f9e683850dfd7`.
Labels, freeze manifest and historical pilot results remain untouched. No secrets,
development records, Gemini/PayPal calls or frontend changes. Running backends need
their normal code reload/restart to use v2; none was initiated by this task.
