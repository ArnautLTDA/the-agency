"""Guardrail Gateway Microservice Main Application (Port :3007)."""

from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, UploadFile, File, Form
from loguru import logger
from pydantic import BaseModel

from agency_common.auth import AgencyKeyMiddleware
from config import settings
from mcp_server import create_guardrail_mcp_server
from services.llama_guard import LlamaGuardClient
from services.whisper import WhisperClient

whisper_client = WhisperClient()
llama_guard_client = LlamaGuardClient()
mcp_server = create_guardrail_mcp_server(
    whisper_client=whisper_client,
    llama_guard_client=llama_guard_client,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Guardrail Gateway Service starting on port {port}...", port=settings.GUARDRAIL_PORT)
    yield
    logger.info("Guardrail Gateway Service shutting down...")


app = FastAPI(
    title="Guardrail Gateway Microservice",
    description="Groq Whisper transcription and Llama Guard 3 security filter",
    version="0.1.0",
    lifespan=lifespan,
)

# Apply X-Agency-Key middleware (exempting health, docs)
app.add_middleware(
    AgencyKeyMiddleware,
    exempt_paths={
        "/health",
        "/api/v1/health",
        "/api/v1/guardrail/health",
        "/docs",
        "/openapi.json",
    },
)


class InspectRequest(BaseModel):
    text: str


@app.get("/api/v1/health")
@app.get("/api/v1/guardrail/health")
async def health_check() -> dict[str, Any]:
    """Healthcheck endpoint for guardrail gateway."""
    return {
        "status": "healthy",
        "service": "guardrail-gateway",
        "port": settings.GUARDRAIL_PORT,
    }


@app.post("/api/v1/guardrail/inspect")
async def inspect_endpoint(request: InspectRequest) -> dict[str, Any]:
    """Inspects text for prompt injection and threats."""
    decision = await llama_guard_client.inspect(request.text)
    return decision.model_dump()


@app.post("/api/v1/whisper/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)) -> dict[str, Any]:
    """Transcribes an uploaded audio file."""
    audio_bytes = await file.read()
    result = await whisper_client.transcribe_audio_bytes(
        audio_bytes=audio_bytes,
        filename=file.filename or "audio.ogg",
        mime_type=file.content_type or "audio/ogg",
    )
    return result.model_dump()


# Mount MCP SSE app at root
sse_app = mcp_server.sse_app()
app.mount("/", sse_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.GUARDRAIL_PORT, reload=False)
