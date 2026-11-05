from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agreements.router import router as agreements_router
from app.bookings.router import router as bookings_router
from app.cancellations.router import router as cancellation_router
from app.clarifications.corrections import router as correction_reviews_router
from app.clarifications.replies import router as clarification_replies_router
from app.clarifications.router import router as clarifications_router
from app.comparisons.router import router as comparisons_router
from app.core.body_limit import RequestBodyLimit
from app.core.database import get_admission_engine, get_engine
from app.demo_sessions.headers import PrivateDemoHeaders
from app.demo_sessions.router import router as demo_sessions_router
from app.drafts.router import router as drafts_router
from app.evidence.router import router as evidence_router
from app.health.router import router as health_router
from app.hosting.middleware import HostingBoundary
from app.hosting.router import router as template_router
from app.payments.router import router as payments_router
from app.payments.webhooks import router as paypal_webhooks_router
from app.policy_consistency.router import router as policy_consistency_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    get_engine().dispose()
    get_admission_engine().dispose()


app = FastAPI(title="BeforePay API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestBodyLimit)
app.add_middleware(HostingBoundary)
app.add_middleware(PrivateDemoHeaders)
app.include_router(demo_sessions_router)
app.include_router(template_router)
app.include_router(health_router)
app.include_router(bookings_router)
app.include_router(evidence_router)
app.include_router(drafts_router)
app.include_router(agreements_router)
app.include_router(comparisons_router)
app.include_router(clarifications_router)
app.include_router(correction_reviews_router)
app.include_router(clarification_replies_router)
app.include_router(cancellation_router)
app.include_router(policy_consistency_router)
app.include_router(payments_router)
app.include_router(paypal_webhooks_router)
