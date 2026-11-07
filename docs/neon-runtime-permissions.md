# Neon runtime permissions

**Sandbox grant update — 7 November 2026:** the exact [payment grant script](hosted-sandbox-payments.md#owner-grants-applied--7-november-2026)
was separately authorised and applied to the same database/role. The inventory
below includes those narrow additions. Readiness rejects sandbox opt-in if the
required grants are missing. The later hosted capture is user-reported manual
evidence, distinct from the rolled-back SQL permission probes.

Applied 2026-11-05 to project `beforepay-demo` (`super-hat-76778640`), branch
`production` (`br-shy-dawn-b3vw2kgo`), database `beforepay_demo_2026` only.
Revision remains `0015_demo_templates`. Migration and table ownership stays with
`neondb_owner`; runtime login is `beforepay_demo_runtime`.

## Explicit grants

| Operation | Objects |
| --- | --- |
| SELECT | All 25 currently named public tables, including read-only migration metadata, catalogue/marker and payment history. Grants name each table; they do not automatically cover future tables. |
| INSERT | `bookings`, `demo_sessions`, `demo_admissions`, `evidence_sources`, `evidence_pages`, `draft_versions`, `agreement_versions`, `agreement_confirmations`, `merchant_booking_versions`, `booking_comparisons`, `cancellation_rule_versions`, `cancellation_rule_approvals`, `checkout_approvals`, `clarification_suggestions`, `clarification_replies`, `clarification_correction_reviews`, `policy_consistency_checks`; added 7 November: `payment_attempts`, `payment_events`, `sandbox_receipts`. |
| UPDATE, column only | `demo_sessions.revoked_at`, `demo_admissions.finished_at`, `demo_admission_control.circuit_reason`, `bookings.owner_session_id`; added 7 November: `payment_attempts.order_id`, `capture_id`, `status`, `error_code`, `capture_requested_at`, `updated_at`. |
| Database/schema | Existing CONNECT and public-schema USAGE only; no database/schema CREATE or TEMP. |
| Sequences | None. Both existing sequences belong to operator-managed singleton tables, which runtime cannot insert into. Application identifiers use UUIDs. |
| Application functions | No explicit EXECUTE grants. Existing five functions are invoker-mode trigger functions; trigger execution needs no runtime direct-call grant. |

The booking column UPDATE grant is needed by SQLAlchemy booking row locks:
`FOR SHARE` for safe HTTP reads and `FOR UPDATE` for mutations/internal callers.
The enabled ownership trigger rejects actual
changes to `owner_session_id`; runtime cannot update the booking title or other
columns. No trigger was changed or disabled.

Runtime cannot INSERT into `alembic_version`, `demo_deployment`, `demo_templates`,
`demo_admission_control` or `paypal_webhook_events`. No DELETE, TRUNCATE, REFERENCES, TRIGGER, table-wide
UPDATE, ownership or grant options were granted. Immutable history remains
append-only, with existing database triggers intact.

Checkout approval INSERT supports the separate explicit approval action; it is
not proof of payment. Public-mode order creation, capture and provider reconciliation
default off; explicit sandbox opt-in uses the narrow payment grants above.
Only verified capture may establish a receipt through the application. Live
payments and hosted webhooks remain disabled.

The 7 November grant verification authenticated as `beforepay_demo_runtime` and
exercised payment inserts, permitted operational updates and **12 rejection checks**
within an explicit rollback. All probe records disappeared; all **25 table counts
and fingerprints** and **20 trigger definitions/states** matched before/after.
Revision remained `0015_demo_templates`, tables remained owned by `neondb_owner`,
and runtime retained zero admin memberships and no SECURITY DEFINER path. This
verified SQL privileges and protections, not a PayPal response. The user subsequently
reported the separate [hosted capture and refresh persistence](hosted-sandbox-payments.md#user-verified-hosted-sandbox-capture--7-november-2026).

## Function and default-privilege audit

No SECURITY DEFINER functions were present in the database. All five public
trigger functions had implicit PUBLIC EXECUTE; this was revoked, and effective
runtime EXECUTE on those functions is now false. Built-in catalog functions used
for time, UUIDs and transaction-level advisory locks retain PostgreSQL's existing
permissions. No blanket function EXECUTE was granted.

`ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner REVOKE EXECUTE ON FUNCTIONS FROM
PUBLIC` closes implicit execution of future owner-created functions in this
database. Future functions need explicit review. No automatic runtime table or
sequence grants were added. Existing provider-managed `cloud_admin` defaults for
`neon_superuser` were inspected and left intact; runtime has no membership in
that role or the owner role. PUBLIC has no table grants or schema CREATE here.

## Verification scope and remaining setup

Verification uses a real TLS connection authenticated as the runtime role, not
owner impersonation. Synthetic session/booking/source and admission operations
are enclosed in an external transaction and rolled back. Independently committing
admission services are bound to the same connection with nested savepoints for
this check, preventing persistent charges or verification records. This verifies
SQL permissions and service guards; it is not a hosted HTTP, proxy, concurrent
budget or provider test. Empty `INSERT ... SELECT ... WHERE false` checks validate
the remaining append grants without fabricating AI drafts or approvals.

At the original 5 November checkpoint, live database checks passed for all 25 read grants, 17 append grants, denied
inserts into eight operator/payment tables, denied DELETE/TRUNCATE across all 25
tables, immutable-table UPDATE denial, sequence denial, schema/temporary-object
creation denial, owner/admin escalation denial and trigger disabling/direct-call
denial. Actual application functions successfully issued/revoked sessions, created
a booking, locked it and attached a source. Per-session booking, shared source and
shared session limits, cross-session access denial, AI-off/circuit rejection and
one-time admission completion were verified. Changing booking ownership was
rejected by its existing trigger. No provider function ran.

At the permission-verification checkpoint, independent owner audit confirmed all 20 protection triggers enabled,
25 tables still owner-controlled, revision unchanged and zero application rows.
Only the original revision row and admission-control singleton remain; its circuit
is still NULL. No sequence privileges, PUBLIC table grants or SECURITY DEFINER
functions were found. These checks are separate from earlier mocked regression
tests; no full regression suite or hosted deployment was run for this operation.

Subsequent authorised [owner template setup](hosting-preparation.md#using-templates-without-inventing-saved-history)
installed one marker and two authored templates on 2026-11-05. Its second run was
idempotent; runtime database-readiness and exact catalogue reads passed, and
runtime writes to both tables were rejected. No session/booking/payment records
were created, and existing grants/triggers were unchanged. Hosted HTTP readiness
still needs deployment verification. Runtime cannot run setup or migrations.
At that template checkpoint public AI was disabled and payment writes were not
granted. The later sandbox grants above do not add webhook recording privileges;
hosted webhook exposure remains disabled. Runtime still cannot run setup/migrations.

Session ownership is enforced by the backend, not PostgreSQL RLS. The runtime
credential is a backend secret; never expose it to judges or browsers. All allowed
mutable operational columns remain governed by existing service logic and
applicable triggers; column privileges alone do not enforce every allowed state
transition. No authentication/permission redesign was added.

No local environment file, local database or `neondb` was changed. This permission
operation performed no deployment, migration, persistent seed or provider call;
the later template-only setup is recorded separately above.
