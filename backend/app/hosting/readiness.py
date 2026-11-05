from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

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
    try:
        name = session.scalar(text("SELECT current_database()"))
        revision = session.scalar(text("SELECT version_num FROM alembic_version"))
        marker = session.execute(
            text(
                "SELECT database_name, template_digest FROM demo_deployment WHERE id=1"
            )
        ).one_or_none()
        triggers = set(
            session.scalars(
                text(
                    "SELECT tgname FROM pg_trigger WHERE tgenabled='O' "
                    "AND NOT tgisinternal"
                )
            )
        )
        control = session.scalar(
            text("SELECT count(*) FROM demo_admission_control WHERE id=1")
        )
        owner_column = session.scalar(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='bookings' "
                "AND column_name='owner_session_id'"
            )
        )
        catalogue = session.execute(
            text("SELECT key, version, content, fingerprint FROM demo_templates")
        ).all()
        catalogue_valid = {
            (row.key, row.version, row.fingerprint) for row in catalogue
        } == {(row["key"], row["version"], row["fingerprint"]) for row in TEMPLATES}
        catalogue_valid = catalogue_valid and all(
            row.content
            == next(
                t["content"]
                for t in TEMPLATES
                if t["key"] == row.key and t["version"] == row.version
            )
            for row in catalogue
        )
        safe_role = True
        if settings.vercel:
            safe_role = session.scalar(
                text("""
                SELECT NOT (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole)
                  AND NOT has_database_privilege(current_user,
                        current_database(), 'CREATE')
                  AND NOT has_schema_privilege(current_user, 'public', 'CREATE')
                  AND NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public'
                                  AND tableowner=current_user)
                  AND NOT has_table_privilege(current_user,
                        'public.demo_admissions', 'TRUNCATE')
                FROM pg_roles WHERE rolname=current_user
            """)
            )
        if (
            name == settings.public_demo_database
            and revision == REVISION
            and marker is not None
            and tuple(marker) == (name, TEMPLATE_DIGEST)
            and TRIGGERS <= triggers
            and control == 1
            and owner_column == 1
            and safe_role
            and catalogue_valid
        ):
            return
    except SQLAlchemyError:
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
