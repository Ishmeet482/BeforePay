"""Explicit template-only setup. Never imports local environment files or bookings."""

import argparse

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import Base
from app.hosting.models import DemoDeployment, DemoTemplate
from app.hosting.readiness import REVISION
from app.hosting.templates import TEMPLATE_DIGEST, TEMPLATES


def setup(engine, expected_database):
    if not expected_database or expected_database in {
        "contextkey",
        "postgres",
        "template0",
        "template1",
    }:
        raise ValueError("Refusing a development/system database")
    with Session(engine) as session, session.begin():
        session.execute(text("SELECT pg_advisory_xact_lock(18632871, 3)"))
        if session.scalar(text("SELECT current_database()")) != expected_database:
            raise ValueError("Dedicated database name does not match")
        if session.scalar(text("SELECT version_num FROM alembic_version")) != REVISION:
            raise ValueError("Apply the expected migrations explicitly before setup")
        marker = session.get(DemoDeployment, 1)
        if marker is None:
            # All feature models are registered by importing main; no startup/run.
            from app import main  # noqa: F401

            for table in Base.metadata.sorted_tables:
                if table.name in {
                    "demo_admission_control",
                    "demo_templates",
                    "demo_deployment",
                }:
                    continue
                if session.scalar(select(func.count()).select_from(table)):
                    raise ValueError(
                        "Unmarked database contains application records; "
                        "refusing adoption"
                    )
            session.add(
                DemoDeployment(
                    id=1,
                    database_name=expected_database,
                    template_digest=TEMPLATE_DIGEST,
                )
            )
        elif (
            marker.database_name != expected_database
            or marker.template_digest != TEMPLATE_DIGEST
        ):
            raise ValueError("Deployment marker differs; manual review required")
        expected_keys = {(row["key"], row["version"]) for row in TEMPLATES}
        if any(
            (row.key, row.version) not in expected_keys
            for row in session.scalars(select(DemoTemplate))
        ):
            raise ValueError("Unknown template versions require manual review")
        for template in TEMPLATES:
            existing = session.get(DemoTemplate, (template["key"], template["version"]))
            if existing is None:
                session.add(DemoTemplate(**template))
            elif (
                existing.fingerprint != template["fingerprint"]
                or existing.content != template["content"]
            ):
                raise ValueError("Template content differs; refusing overwrite")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-name", required=True)
    parser.add_argument(
        "--acknowledge-dedicated-synthetic-db", action="store_true", required=True
    )
    args = parser.parse_args()
    # DATABASE_URL must be explicitly exported by the operator; never use .env.
    import os

    if not os.environ.get("DATABASE_URL"):
        parser.error(
            "Export the dedicated migration/admin DATABASE_URL; no local default"
        )
    try:
        settings = Settings(_env_file=None)
        engine = create_engine(
            settings.database_url.get_secret_value(),
            connect_args={"connect_timeout": 3, "prepare_threshold": None},
        )
        try:
            setup(engine, args.database_name)
        finally:
            engine.dispose()
    except Exception:
        parser.exit(
            1,
            "Synthetic setup refused or unavailable; no partial changes committed. "
            "Check database identity, revision and existing state privately.\n",
        )
    print(
        "Synthetic template catalogue ready. No bookings, AI results, "
        "approvals or receipts created."
    )


if __name__ == "__main__":
    main()
