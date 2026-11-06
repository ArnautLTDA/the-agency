"""FastAPI Route Definitions for Health, Agent Run Dispatch and Streaming (TC-007, TC-008, TC-012 to TC-019)."""

import asyncio
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.api.sse import SSEBroker, get_sse_broker
from src.config import get_settings
from src.models.database import get_session, get_session_factory
from src.models.entities import AgentRun, RunStatus
from src.runner.agent_runner import AgentRunner, load_agent_profile
from src.services.currency import get_currency_service
from src.services.pool import AgentPool, get_agent_pool


router = APIRouter(prefix="/api/v1")


class AgentRunRequest(BaseModel):
    agent_id: str = Field(..., description="Agent profile identifier slug (e.g. homologation_agent)")
    task: str = Field(..., min_length=1, max_length=100000, description="Task instruction prompt")
    workspace_dir: str = Field(default="workspaces/clients/default", description="Workspace directory")
    max_iterations: int = Field(default=25, gt=0, le=100, description="Max iterations ceiling")


class AgentRunResponse(BaseModel):
    run_id: uuid.UUID
    status: str
    stream_url: str


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_session)):
    """Health check endpoint validating SQLite, currency service, and credentials (TC-007, TC-008)."""
    settings = get_settings()
    currency_service = get_currency_service()

    is_db_healthy = False
    try:
        res = await session.exec(text("SELECT 1"))
        is_db_healthy = res.scalar() == 1
    except Exception:
        is_db_healthy = False

    usd_brl_rate = await currency_service.get_usd_brl_rate()
    has_api_key = bool(settings.GEMINI_API_KEY)

    if not is_db_healthy or not has_api_key:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": "connected" if is_db_healthy else "disconnected",
                "gemini_api_key_configured": has_api_key,
                "usd_brl_rate": usd_brl_rate,
            },
        )

    return {
        "status": "healthy",
        "database": "connected",
        "gemini_api_key_configured": has_api_key,
        "usd_brl_rate": usd_brl_rate,
    }


@router.post(
    "/agent/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AgentRunResponse,
)
async def dispatch_agent_run(
    request: AgentRunRequest,
    session: AsyncSession = Depends(get_session),
    pool: AgentPool = Depends(get_agent_pool),
    sse: SSEBroker = Depends(get_sse_broker),
):
    """Asynchronously dispatches an agent task to the concurrency pool (TC-012 to TC-015)."""
    # TC-013: Validate agent YAML exists before accepting
    try:
        load_agent_profile(request.agent_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent profile '{request.agent_id}' not found.",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid profile for '{request.agent_id}': {exc}",
        )

    run_id = uuid.uuid4()
    run = AgentRun(
        run_id=run_id,
        agent_id=request.agent_id,
        task=request.task,
        workspace_dir=request.workspace_dir,
        status=RunStatus.QUEUED,
        max_iterations=request.max_iterations,
    )
    session.add(run)
    await session.commit()

    # Callback to stream events to SSE broker
    async def sse_event_callback(event_type: str, data: dict[str, Any]):
        await sse.publish(run_id=run_id, event_type=event_type, data=data)

    runner = AgentRunner(
        run_id=run_id,
        agent_id=request.agent_id,
        task=request.task,
        workspace_dir=Path(request.workspace_dir),
        session_factory=get_session_factory(session.bind),
        max_iterations=request.max_iterations,
        sse_callback=sse_event_callback,
    )

    # Dispatch to background pool (non-blocking, releases HTTP connection immediately)
    asyncio.create_task(pool.submit(run_id=run_id, coro=runner.run()))

    return AgentRunResponse(
        run_id=run_id,
        status="queued",
        stream_url=f"/api/v1/events/stream?run_id={run_id}",
    )


@router.get("/agent/run/{run_id}")
async def get_agent_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Retrieves current execution state and financial metrics for a run (TC-016, TC-017)."""
    stmt = select(AgentRun).where(AgentRun.run_id == run_id)
    result = await session.exec(stmt)
    run = result.one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with ID '{run_id}' not found.",
        )

    return {
        "run_id": run.run_id,
        "agent_id": run.agent_id,
        "status": run.status.value if hasattr(run.status, "value") else str(run.status),
        "iterations": run.iterations,
        "max_iterations": run.max_iterations,
        "total_prompt_tokens": run.total_prompt_tokens,
        "total_completion_tokens": run.total_completion_tokens,
        "total_cached_tokens": run.total_cached_tokens,
        "total_cost_usd": run.total_cost_usd,
        "total_cost_brl": run.total_cost_brl,
        "result_summary": run.result_summary,
        "error_message": run.error_message,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "completed_at": run.completed_at,
    }


@router.get("/events/stream")
async def sse_event_stream(
    run_id: uuid.UUID | None = Query(default=None),
    sse: SSEBroker = Depends(get_sse_broker),
):
    """Server-Sent Events streaming feed filtered by run_id or global (TC-018, TC-019)."""
    async def event_generator():
        async for event in sse.subscribe(run_id=run_id):
            yield event.encode()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
