from fastapi import APIRouter
from sqlalchemy import select

from app.bookings.router import DatabaseSession
from app.hosting.models import DemoTemplate

router = APIRouter(prefix="/api/demo-templates", tags=["synthetic templates"])


@router.get("")
def templates(session: DatabaseSession):
    return [
        {
            "key": row.key,
            "version": row.version,
            "fingerprint": row.fingerprint,
            **row.content,
        }
        for row in session.scalars(
            select(DemoTemplate).order_by(DemoTemplate.key, DemoTemplate.version)
        )
    ]
