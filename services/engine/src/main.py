"""FastAPI Application entry point with Lifespan lifecycle management."""

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger

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

    # 2. Run Crash Recovery Sweep for orphaned runs from previous session
    async with session_factory() as session:
        recovered = await run_crash_recovery(session)
        if recovered > 0:
            logger.warning(f"Crash Recovery: Recovered {recovered} orphaned tasks.")

    # 3. Currency Rate Prefetch
    currency = get_currency_service()
    rate = await currency.get_usd_brl_rate()
    logger.info(f"USD/BRL Exchange Rate initialized: R$ {rate:.4f}")

    logger.info(f"The Agency Engine successfully started on {settings.HOST}:{settings.PORT}")
    yield

    # Shutdown routines
    logger.info("Shutting down The Agency Engine...")
    pool = get_agent_pool()
    await pool.shutdown()
    await engine.dispose()
    logger.info("Engine shutdown complete.")


def create_app(db_url: str | None = None) -> FastAPI:
    """Factory function for creating and configuring the FastAPI app instance."""
    app = FastAPI(
        title="The Agency Engine",
        version="0.1.0",
        description="Standalone Autonomous Agent Runtime Core",
        lifespan=lifespan,
    )
    app.state.db_url = db_url
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
