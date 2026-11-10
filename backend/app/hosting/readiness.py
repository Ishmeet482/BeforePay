from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.hosting.diagnostics import log_database_failure
from app.hosting.templates import TEMPLATE_DIGEST, TEMPLATES

REVISION = "0015_demo_templates"
TRIGGERS = {
    "bookings_owner_immutable",
    "demo_admissions_immutable",
    "sandbox_receipts_immutable",
    "paypal_webhook_events_immutable",
    "demo_templates_immutable",
    "demo_deployment_immutable",
}


def require_public_database(session, settings):
    if not settings.public_demo_mode:
        return
    check = "database_identity"
    try:
        name = session.scalar(text("SELECT current_database()"))
        check = "readiness_snapshot"
        # All invariants are still checked on every public request. One SQL
        # snapshot avoids seven/eight sequential network round trips; no cache.
        snapshot = session.scalar(
            text("""
            SELECT jsonb_build_object(
              'revision', (SELECT version_num FROM alembic_version),
              'marker', (SELECT jsonb_build_array(database_name, template_digest)
                         FROM demo_deployment WHERE id=1),
              'triggers', (SELECT coalesce(jsonb_agg(tgname), '[]'::jsonb)
                           FROM pg_trigger WHERE tgenabled='O' AND NOT tgisinternal),
              'control', (SELECT count(*) FROM demo_admission_control WHERE id=1),
              'owner_column', (SELECT count(*) FROM information_schema.columns
                  WHERE table_schema='public' AND table_name='bookings'
                    AND column_name='owner_session_id'),
              'catalogue', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                  'key', key, 'version', version, 'content', content,
                  'fingerprint', fingerprint)), '[]'::jsonb) FROM demo_templates),
              'safe_role', CASE WHEN :runtime THEN (
                SELECT NOT (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole)
                  AND NOT has_database_privilege(current_user,
                        current_database(), 'CREATE')
                  AND NOT has_schema_privilege(current_user, 'public', 'CREATE')
                  AND NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public'
                                  AND tableowner=current_user)
                  AND NOT has_table_privilege(current_user,
                        'public.demo_admissions', 'TRUNCATE')
                FROM pg_roles WHERE rolname=current_user
              ) ELSE true END,
              'payment_role', CASE WHEN :payment THEN (
                SELECT has_table_privilege(current_user, 'payment_attempts', 'INSERT')
                  AND has_table_privilege(current_user, 'payment_events', 'INSERT')
                  AND has_table_privilege(current_user, 'sandbox_receipts', 'INSERT')
                  AND bool_and(has_column_privilege(current_user,
                      'payment_attempts', col, 'UPDATE'))
                FROM unnest(ARRAY['order_id','capture_id','status','error_code',
                    'capture_requested_at','updated_at']) AS col
              ) ELSE true END
            )
            """),
            {
                "runtime": settings.vercel,
                "payment": settings.vercel and settings.public_sandbox_payments_enabled,
            },
        )
        revision, marker = snapshot["revision"], snapshot["marker"]
        triggers = set(snapshot["triggers"])
        control, owner_column = snapshot["control"], snapshot["owner_column"]
        catalogue = snapshot["catalogue"]
        catalogue_valid = {
            (row["key"], row["version"], row["fingerprint"]) for row in catalogue
        } == {(row["key"], row["version"], row["fingerprint"]) for row in TEMPLATES}
        catalogue_valid = catalogue_valid and all(
            row["content"]
            == next(
                t["content"]
                for t in TEMPLATES
                if t["key"] == row["key"] and t["version"] == row["version"]
            )
            for row in catalogue
        )
        safe_role, payment_role = snapshot["safe_role"], snapshot["payment_role"]
        checks = {
            "database_identity": name == settings.public_demo_database,
            "migration_revision": revision == REVISION,
            "deployment_marker": marker is not None
            and tuple(marker) == (name, TEMPLATE_DIGEST),
            "immutable_triggers": TRIGGERS <= triggers,
            "admission_control": control == 1,
            "ownership_column": owner_column == 1,
            "runtime_privileges": bool(safe_role),
            "payment_runtime_privileges": bool(payment_role),
            "template_catalogue": catalogue_valid,
        }
        if all(checks.values()):
            return
        log_database_failure(
            "invariants",
            failed_checks=[key for key, valid in checks.items() if not valid],
        )
    except SQLAlchemyError as error:
        log_database_failure(check, error=error)
        session.rollback()
    raise HTTPException(
        503,
        {
            "code": "public_setup_required",
            "message": (
                "Dedicated demo database, migrations, templates or "
                "protections are not ready. Ask the organiser; "
                "no action was performed."
            ),
        },
    )
