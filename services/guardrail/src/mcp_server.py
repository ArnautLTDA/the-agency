"""Native MCP Server registering Guardrail inspection and transcription tools (:3007)."""

from typing import Any
from mcp.server.mcpserver import MCPServer

from services.llama_guard import LlamaGuardClient
from services.whisper import WhisperClient


def create_guardrail_mcp_server(
    whisper_client: WhisperClient | None = None,
    llama_guard_client: LlamaGuardClient | None = None,
) -> MCPServer:
    """Builds and configures the guardrail-gateway MCP server instance."""
    server = MCPServer(
        name="guardrail-gateway",
        version="0.1.0",
        instructions="Official Agency Guardrail Gateway MCP Server",
    )
    whisper = whisper_client or WhisperClient()
    guard = llama_guard_client or LlamaGuardClient()

    @server.tool(
        name="inspect_content",
        description="Inspects text for prompt injections, jailbreaks, and unsafe content via Llama Guard 3 (TC-110).",
    )
    async def inspect_content(text: str) -> dict[str, Any]:
        decision = await guard.inspect(text)
        return decision.model_dump()

    @server.tool(
        name="transcribe_audio",
        description="Transcribes audio base64 payload into text using Groq Whisper large-v3 (TC-109).",
    )
    async def transcribe_audio(audio_base64: str, mime_type: str = "audio/ogg") -> dict[str, Any]:
        result = await whisper.transcribe_base64(audio_base64, mime_type=mime_type)
        return result.model_dump()

    return server
