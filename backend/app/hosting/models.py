from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DemoTemplate(Base):
    __tablename__ = "demo_templates"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[dict] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(String(64))


class DemoDeployment(Base):
    __tablename__ = "demo_deployment"
    id: Mapped[int] = mapped_column(primary_key=True)
    database_name: Mapped[str] = mapped_column(String(100))
    template_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
