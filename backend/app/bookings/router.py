from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admission.service import reserve
from app.bookings.models import Booking
from app.bookings.schemas import BookingCreate, BookingRead
from app.demo_sessions.service import current_owner, owned_session

router = APIRouter(prefix="/api/bookings", tags=["bookings"])
DatabaseSession = Annotated[Session, Depends(owned_session)]


def require_booking(session: Session, booking_id: UUID) -> Booking:
    owner = current_owner(session)
    booking = session.scalar(select(Booking).where(Booking.id == booking_id))
    if booking is None or (owner is not None and booking.owner_session_id != owner):
        raise HTTPException(404, "Booking not found")
    return booking


def lock_booking(session: Session, booking_id: UUID) -> Booking:
    booking = session.scalar(
        select(Booking).where(Booking.id == booking_id).with_for_update()
    )
    owner = current_owner(session)
    if booking is None or (owner is not None and booking.owner_session_id != owner):
        raise HTTPException(404, "Booking not found")
    return booking


@router.post("", response_model=BookingRead, status_code=201)
def create_booking(body: BookingCreate, session: DatabaseSession) -> Booking:
    reserve(session, "booking", "create_booking", {})
    booking = Booking(title=body.title, owner_session_id=current_owner(session))
    session.add(booking)
    session.commit()
    session.refresh(booking)
    return booking


@router.get("", response_model=list[BookingRead])
def list_bookings(
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Booking]:
    return list(
        session.scalars(
            select(Booking)
            .where(Booking.owner_session_id == current_owner(session))
            .order_by(Booking.created_at.desc(), Booking.id)
            .offset(offset)
            .limit(limit)
        )
    )


@router.get("/{booking_id}", response_model=BookingRead)
def get_booking(booking_id: UUID, session: DatabaseSession) -> Booking:
    return require_booking(session, booking_id)
