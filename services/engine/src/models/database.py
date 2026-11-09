"""Database connection manager with strict SQLite WAL mode."""

from collections.abc import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import get_settings


def get_async_engine(db_url: str | None = None) -> AsyncEngine:
    """Creates an async SQLAlchemy engine with WAL mode and performance pragmas."""
    if db_url is None:
        db_url = get_settings().DATABASE_URL

    connect_args = {}
    if "sqlite" in db_url:
        connect_args["check_same_thread"] = False

    engine = create_async_engine(
        db_url,
        echo=False,
        future=True,
        connect_args=connect_args,
    )

    if "sqlite" in db_url:
        @event.listens_for(engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA auto_vacuum = INCREMENTAL;")
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=5000;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    return engine


def get_session_factory(engine: AsyncEngine) -> sessionmaker:
    """Returns an async sessionmaker for the given engine."""
    return sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def create_db_and_tables(engine: AsyncEngine) -> None:
    """Creates all database tables defined in SQLModel entities."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


# Global instances for runtime dependency injection
_engine: AsyncEngine | None = None
_session_factory: sessionmaker | None = None


def init_db(db_url: str | None = None) -> tuple[AsyncEngine, sessionmaker]:
    """Initializes global engine and sessionmaker."""
    global _engine, _session_factory
    _engine = get_async_engine(db_url)
    _session_factory = get_session_factory(_engine)
    return _engine, _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an async database session."""
    global _session_factory
    if _session_factory is None:
        init_db()
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session
