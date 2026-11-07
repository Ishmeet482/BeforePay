"""Allowlisted readiness diagnostics; never log exception prose or SQL."""

import json
import logging

from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from app.core.config import Settings

logger = logging.getLogger("uvicorn.error.beforepay.hosting")
SQLSTATES = frozenset(
    {
        "08001",
        "08003",
        "08006",
        "28P01",
        "3D000",
        "42501",
        "42703",
        "42P01",
        "53300",
        "55P03",
        "57014",
        "57P01",
        "57P02",
        "57P03",
    }
)


def log_settings_failure(error):
    # Pydantic messages/context/input may contain entire credential-bearing URLs.
    fields = {
        item["loc"][0]
        for item in error.errors(
            include_input=False, include_context=False, include_url=False
        )
        if item["loc"] and item["loc"][0] in Settings.model_fields
    }
    logger.warning(
        "public_setup_failure %s",
        json.dumps(
            {
                "boundary": "settings_validation",
                "exception_type": "ValidationError",
                "fields": sorted(fields),
                "model_validation": not bool(fields),
            },
            sort_keys=True,
        ),
    )


def log_database_failure(check, *, error=None, failed_checks=()):
    # All check names are application constants; no observed database values.
    exception_type, sqlstate = None, None
    if error is not None:
        exception_type = "SQLAlchemyError"
        for cls, name in (
            (PoolTimeout, "PoolTimeout"),
            (OperationalError, "OperationalError"),
            (ProgrammingError, "ProgrammingError"),
            (DBAPIError, "DBAPIError"),
        ):
            if isinstance(error, cls):
                exception_type = name
                break
        if isinstance(error, DBAPIError):
            state = getattr(error.orig, "sqlstate", None)
            sqlstate = (
                state if isinstance(state, str) and state in SQLSTATES else "OTHER"
            )
    logger.warning(
        "public_setup_failure %s",
        json.dumps(
            {
                "boundary": "database_readiness",
                "check": check,
                "exception_type": exception_type,
                "sqlstate": sqlstate,
                "failed_checks": list(failed_checks),
            },
            sort_keys=True,
        ),
    )
