from sqlalchemy import create_engine, pool

from alembic import context
from app.admission.models import Admission, AdmissionControl  # noqa: F401
from app.agreements.models import AgreementConfirmation, AgreementVersion  # noqa: F401
from app.bookings.models import Booking  # noqa: F401
from app.cancellations.models import CancellationRuleApproval, CancellationRuleVersion  # noqa: F401
from app.clarifications import models as clarification_models  # noqa: F401
from app.comparisons.models import BookingComparison, ProposalVersion  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base
from app.demo_sessions.models import DemoSession  # noqa: F401
from app.drafts.models import DraftVersion  # noqa: F401
from app.evidence.models import EvidencePage, EvidenceSource  # noqa: F401
from app.hosting.models import DemoDeployment, DemoTemplate  # noqa: F401
from app.payments import models as payment_models  # noqa: F401
from app.policy_consistency import models as consistency_models  # noqa: F401

target_metadata = Base.metadata
database_url = get_settings().database_url.get_secret_value()

if context.is_offline_mode():
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    context.configure(
        connection=context.config.attributes["connection"],
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
