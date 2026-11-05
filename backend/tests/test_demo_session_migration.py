"""Upgrade a separate disposable 0012 database containing synthetic legacy data."""

import hashlib
import json
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command


def snapshot(connection):
    tables = connection.scalars(
        text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' "
            "AND tablename NOT IN ('alembic_version', 'demo_sessions', "
            "'demo_admissions', 'demo_admission_control', "
            "'demo_templates', 'demo_deployment') "
            "ORDER BY tablename"
        )
    ).all()
    result = {}
    for table in tables:
        # Catalogue names only. Remove the sole additive column for comparison.
        rows = connection.scalars(
            text(f"SELECT to_jsonb(row) - 'owner_session_id' FROM \"{table}\" row")
        ).all()
        canonical = sorted(json.dumps(row, sort_keys=True) for row in rows)
        result[table] = (
            len(rows),
            hashlib.sha256(json.dumps(canonical).encode()).hexdigest(),
        )
    return result


@pytest.mark.parametrize(
    "revision", ["0013_demo_sessions", "0014_public_admission", "0015_demo_templates"]
)
def test_upgrade_preserves_legacy_counts_and_fingerprints(postgres_engine, revision):
    name = "contextkey_test_migration_" + uuid4().hex
    admin = create_engine(
        postgres_engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    engine = None
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        engine = create_engine(postgres_engine.url.set(database=name))
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0012_policy_consistency")
            booking, source = uuid4(), uuid4()
            connection.execute(
                text(
                    "INSERT INTO bookings(id,title) "
                    "VALUES (:id,'Synthetic legacy booking')"
                ),
                {"id": booking},
            )
            connection.execute(
                text(
                    "INSERT INTO evidence_sources"
                    "(id,booking_id,source_type,medium,original_text) "
                    "VALUES (:id,:booking,'quotation','pasted_text',"
                    "'Unchanged synthetic terms')"
                ),
                {"id": source, "booking": booking},
            )
            before = snapshot(connection)
            command.upgrade(config, revision)
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == revision
            )
            assert snapshot(connection) == before
            assert (
                connection.scalar(
                    text("SELECT owner_session_id FROM bookings WHERE id=:id"),
                    {"id": booking},
                )
                is None
            )
            assert connection.scalar(text("SELECT count(*) FROM demo_sessions")) == 0
            if revision == "0014_public_admission":
                assert (
                    connection.scalar(text("SELECT count(*) FROM demo_admissions")) == 0
                )
                assert (
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM demo_admission_control "
                            "WHERE id=1 AND circuit_reason IS NULL"
                        )
                    )
                    == 1
                )
                assert (
                    connection.scalar(
                        text(
                            "SELECT tgenabled FROM pg_trigger "
                            "WHERE tgname='demo_admissions_immutable'"
                        )
                    )
                    == "O"
                )
            assert (
                connection.scalar(
                    text(
                        "SELECT tgenabled FROM pg_trigger "
                        "WHERE tgname='bookings_owner_immutable'"
                    )
                )
                == "O"
            )
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()
