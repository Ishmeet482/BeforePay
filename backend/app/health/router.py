from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_session

router = APIRouter(prefix="/api/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["contextkey-api"] = "contextkey-api"


class ReadinessResponse(HealthResponse):
    database: Literal["ok"] = "ok"


@router.get("/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=ReadinessResponse)
def ready(session: Annotated[Session, Depends(get_session)]) -> ReadinessResponse:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # Never return connection strings or database exception details to clients.
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return ReadinessResponse()
