# Guardrail Gateway (Port :3007)

Edge security gate for incoming WhatsApp communication:
- Audio transcription via Groq Whisper (`whisper-large-v3`)
- Safety and prompt injection inspection via Llama Guard 3 (`llama-guard-3-8b`)
- AMQP consumer for `whatsapp.raw`
- Publisher to `whatsapp.inbound` (safe messages) and `telegram.alerts` (security incidents)
- MCP Server exposing inspection and transcription tools
