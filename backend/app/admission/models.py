from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Admission(Base):
    __tablename__ = "demo_admissions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # Validated before admission; deliberately no FK that could wait on booking locks.
    session_id: Mapped[UUID | None] = mapped_column(index=True)
    booking_id: Mapped[UUID | None]
    kind: Mapped[str] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(80))
    input_hash: Mapped[str] = mapped_column(String(64))
    units: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdmissionControl(Base):
    __tablename__ = "demo_admission_control"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    circuit_reason: Mapped[str | None] = mapped_column(String(40))
