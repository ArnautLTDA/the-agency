"""FastAPI Application entry point with Lifespan lifecycle management."""

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api.middleware import RequestIDMiddleware
from src.api.router import router
from src.config import get_settings, setup_logging
from src.models.database import create_db_and_tables, get_async_engine, init_db
from src.services.currency import get_currency_service
from src.services.pool import get_agent_pool
from src.services.recovery import run_crash_recovery


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager managing startup and shutdown routines."""
    settings = get_settings()
    setup_logging(settings)
    logger.info("Initializing The Agency Engine...")

    # 1. Initialize SQLite Database & Tables
    engine, session_factory = init_db(getattr(app.state, "db_url", None))
    await create_db_and_tables(engine)
    logger.info("Database schema initialized with WAL mode.")

    # SEC-019: Auto-upgrade Alembic migrations on startup
    try:
        from pathlib import Path
        from alembic import command
        from alembic.config import Config
        alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
        if alembic_ini_path.exists():
            alembic_cfg = Config(str(alembic_ini_path))
            sync_url = str(engine.url).replace("+aiosqlite", "")
            alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
            command.upgrade(alembic_cfg, "head")
            logger.info("Alembic migrations verified up to head.")
    except Exception as exc:
        logger.warning(f"Alembic auto-upgrade notice: {exc}")

    # 2. Run Crash Recovery Sweep for orphaned runs from previous session
    async with session_factory() as session:
        recovered = await run_crash_recovery(session)
        if recovered > 0:
            logger.warning(f"Crash Recovery: Recovered {recovered} orphaned tasks.")

    # 3. Currency Rate Prefetch
    currency = get_currency_service()
    rate = await currency.get_usd_brl_rate()
    logger.info(f"USD/BRL Exchange Rate initialized: R$ {rate:.4f}")

    # 4. Initialize Queue Service (RabbitMQ / fallback)
    from src.services.queue import get_queue_service
    queue_service = get_queue_service()
    await queue_service.connect()

    # 5. Initialize Supervisor & Discovery (Fail-Fast & Tool Registry)
    import asyncio
    from src.services.supervisor import get_supervisor
    from src.tools.mcp_discovery import get_discovery_service
    supervisor = get_supervisor()
    discovery = get_discovery_service()
    asyncio.create_task(discovery.discover_all(timeout_per_service=1.5))

    logger.info(f"The Agency Engine successfully started on {settings.HOST}:{settings.PORT}")
    yield

    # Shutdown routines
    logger.info("Shutting down The Agency Engine...")
    await supervisor.stop()
    await queue_service.close()
    pool = get_agent_pool()
    await pool.shutdown()
    await engine.dispose()
    logger.info("Engine shutdown complete.")


def create_app(db_url: str | None = None) -> FastAPI:
    """Factory function for creating and configuring the FastAPI app instance."""
    settings = get_settings()
    app = FastAPI(
        title="The Agency Engine",
        version="0.1.0",
        description="Standalone Autonomous Agent Runtime Core",
        lifespan=lifespan,
    )
    app.state.db_url = db_url

    # SEC-023: Request ID tracing middleware
    app.add_middleware(RequestIDMiddleware)

    # SEC-010: Explicit CORS policy
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app


app = create_app()


def start():
    """CLI entrypoint to run the uvicorn server."""
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False,
    )


if __name__ == "__main__":
    start()
