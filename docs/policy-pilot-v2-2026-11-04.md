# Frozen v2: small synthetic live pilot — 2026-11-04

**Six-case synthetic pilot, not general accuracy.** User authorised only cmp-01,
cmp-04, cmp-08, con-01, con-04 and con-08. All six completed sequentially, once
each. No quota/rate-limit/authentication or other provider errors, retries,
fallback, model changes, PayPal calls or development-record access/changes.

## Preserved evidence

[Per-case journal and final report](../backend/evaluations/results/policy-v2-pilot-2026-11-04.jsonl)
contains exact selected inputs/labels, durable start/end checkpoints, structured
outputs, failures, model/response IDs, SDK/prompt versions, dataset hash and scores.
Every record was flushed and fsynced. The exclusive output file has private permissions.

- Requested and returned model, every case: **gemini-3.5-flash-lite**.
- Google GenAI SDK: **2.34.0**. Existing prompts:
  `rental-policy-comparison-v1` and `merchant-deposit-cancellation-consistency-v1`.
- Started **2026-11-04 12:13:34.354184 UTC**; finished
  **2026-11-04 12:14:08.442626 UTC**.
- Frozen canonical dataset SHA-256, verified before configuration and each case:
  `9d1b1ab80ed60ba99e1ad20eb794af99e106922a90874b603a3e16fe8adb5e59`.
- Exact dataset file SHA-256:
  `63cb5bc9f010ee942aea4f17dc22c08541251b43cd545ea18fae86ebd29d2777`.
- Journal SHA-256:
  `fb7c913e6b2806f150dab01ef9c1f0b99b0c4c28b318a5f69a2f9e683850dfd7`.

Normal backend configuration supplied the existing credentials/model at runtime.
Credentials were not printed, exported, edited or recorded. Gemini received only
synthetic clause context, not expected labels/rationales. No database session was created.

## Expected versus actual

| Task | Case | Frozen expectation | Actual | Literal citations | Outcome |
| --- | --- | --- | --- | --- | --- |
| Comparison | cmp-01 | differs | differs | Valid | Expected label |
| Comparison | cmp-04 | matches | matches | Valid | Expected label |
| Comparison | cmp-08 | needs_clarification | **differs** | Valid | **Label mismatch** |
| Consistency | con-01 | potential_contradiction | potential_contradiction | Valid | Expected label |
| Consistency | con-04 | no_contradiction_found | no_contradiction_found | Valid | Expected label |
| Consistency | con-08 | needs_clarification | needs_clarification | Valid | Expected label |

cmp-08 quoted exactly “The deposit is returned after undamaged equipment is
returned.” and “Deposit refundability will be decided later.” It returned `differs`
rather than `needs_clarification`. This fails the intended uncertainty label, but
is **not a false match**. Both statuses block under existing comparison rules;
this pilot did not exercise booking eligibility or approval/payment flows. The
comparison schema has no explanation field, so no unreturned model rationale is
inferred. No prompt/label was changed to fit this response and no case was retried.

con-08 returned uncertainty with both complete clauses, explaining that special
circumstances for deposit refund remain undefined. con-04 recognised the explicit
early-cancellation exception as compatible.

## Separate pilot metrics

These fractions cover only three selected cases per task. Denominators of one
cannot establish dependable performance elsewhere.

| Metric | Comparison | Consistency |
| --- | --- | --- |
| Material-change recall | **1/1** | Not applicable: no earlier-version baseline |
| Contradiction recall | Not applicable | **1/1** |
| False-positive rate on labelled clean cases | **0/1** | **0/1** |
| Literal citation validity | **3/3 cases** | **3/3 cases** |
| Intended uncertainty handling | **0/1**, cmp-08 failed | **1/1** |
| Definitive clean findings on uncertain cases | None | None |
| Provider/schema/reference errors | None | None |

Citation validity uses production side/category, literal quotation and reference
coverage checks. It does not prove semantic correctness or legal completeness.
Other 14 cases were **not run**, including both local missing-input checks; they
are excluded from these pilot denominators, not counted as successes or failures.

## Execution controls and offline checks

The existing full runner only supports an 18-call scope. A dedicated bounded wrapper,
`backend/evaluations/policy_pilot.py`, fixes these six IDs, requires explicit live
flags and `--max-calls 6`, reuses unchanged provider adapters and checkpoints results.
It immediately stops on quota/rate-limit/authentication/configuration errors,
including direct 401/403/429 errors. Other case failures are recorded without retry;
unexpected interruption stops conservatively. Unattempted IDs remain explicit.
A started case without a completion record is uncertain, not permission to rerun.

Before live execution, **four offline mocked safety checks passed**, covering fatal
stop/checkpoint preservation, exact scope/no retries, and default planning without
configuration access. Ruff lint/format passed for wrapper/tests. Those checks are
separate from the six actual provider responses above.

No frozen dataset, prompt, migration, approval guard or business record changed.
This report authorises no additional model requests.
