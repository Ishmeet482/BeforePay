import secrets
from datetime import UTC, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admission.service import reserve
from app.core.database import get_session
from app.demo_sessions.models import DemoSession
from app.demo_sessions.service import (
    COOKIE,
    active_session,
    check_csrf,
    check_origin,
    csrf_token,
    get_settings,
    reject_session,
    token_hash,
)

router = APIRouter(prefix="/api/demo-sessions", tags=["isolated demo sessions"])
Database = Annotated[Session, Depends(get_session)]


def description(record, token):
    return {
        "active": True,
        "expires_at": record.expires_at,
        "csrf_token": csrf_token(token),
    }


@router.post("", status_code=201)
def start(request: Request, response: Response, session: Database):
    check_origin(request, required=True)
    settings = get_settings()
    if not settings.demo_cookie_secure and request.url.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise HTTPException(403, "Insecure cookies require a loopback backend")
    token = request.cookies.get(COOKIE)
    record = active_session(session, token)
    if record is not None:
        # Explicit re-entry/role switching does not rotate scope or extend expiry.
        response.status_code = 200
        return description(record, token)
    token = secrets.token_urlsafe(32)
    reserve(session, "session", "issue_session", {})
    now = session.scalar(select(func.clock_timestamp()))
    record = DemoSession(
        token_hash=token_hash(token),
        expires_at=now + timedelta(seconds=settings.demo_session_ttl_seconds),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.demo_session_ttl_seconds,
        expires=record.expires_at.astimezone(UTC),
        path="/api",
        httponly=True,
        secure=settings.demo_cookie_secure,
        samesite="lax",
    )
    return description(record, token)


@router.get("")
def inspect(request: Request, session: Database):
    check_origin(request)
    token = request.cookies.get(COOKIE)
    record = active_session(session, token)
    if record is None:
        reject_session()
    return description(record, token)


@router.delete("", status_code=204)
def sign_out(request: Request, session: Database):
    check_origin(request, required=True)
    token = request.cookies.get(COOKIE)
    record = active_session(session, token)
    if record is not None:
        check_csrf(request, token)
        record.revoked_at = session.scalar(select(func.clock_timestamp()))
        session.commit()
    response = Response(status_code=204)
    response.delete_cookie(
        COOKIE,
        path="/api",
        secure=get_settings().demo_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response
