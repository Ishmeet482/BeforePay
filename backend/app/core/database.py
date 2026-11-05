from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    return build_engine()


def build_engine(*, admission=False) -> Engine:
    settings = get_settings()
    engine = create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=1 if admission else settings.db_pool_size,
        max_overflow=0 if admission else settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=300,
        connect_args={"connect_timeout": 3, "prepare_threshold": None},
    )
    if settings.public_demo_mode:

        @event.listens_for(engine, "begin")
        def bounded_transaction(connection):
            connection.exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout = '3000ms'")

    return engine


@lru_cache
def get_admission_engine() -> Engine:
    return build_engine(admission=True)


def get_session() -> Iterator[Session]:
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with factory() as session:
        from app.hosting.readiness import require_public_database

        require_public_database(session, get_settings())
        if get_settings().public_demo_mode:
            session.info["admission_bind"] = get_admission_engine()
        yield session
