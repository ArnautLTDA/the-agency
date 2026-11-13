"""AMQP Raw Message Consumer for WhatsApp edge filtering (TC-110, TC-111, TC-112, TC-113)."""

from datetime import datetime, timezone
import json
import uuid
from typing import Any
import aio_pika
import aiosqlite
from loguru import logger

from agency_common.amqp import AMQPMessageEnvelope
from config import settings
from services.llama_guard import GuardrailDecision, LlamaGuardClient
from services.whisper import WhisperClient


class RawWhatsAppConsumer:
    """Consumes raw messages from WhatsApp socket, transcribes voice notes, inspects safety, and routes."""

    def __init__(
        self,
        whisper_client: WhisperClient | None = None,
        llama_guard_client: LlamaGuardClient | None = None,
        db_path: str = settings.DATABASE_PATH,
    ) -> None:
        self.whisper_client = whisper_client or WhisperClient()
        self.llama_guard_client = llama_guard_client or LlamaGuardClient()
        self.db_path = db_path

    async def record_security_incident(
        self,
        sender_jid: str,
        raw_message: str,
        threat_category: str,
        risk_score: float,
        action_taken: str = "silent_drop",
    ) -> None:
        """Persists security incident to central pipeline.db SQLite table."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO security_incidents (sender_jid, raw_message, threat_category, risk_score, action_taken, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sender_jid,
                        raw_message,
                        threat_category,
                        risk_score,
                        action_taken,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                await db.commit()
            logger.info("Security incident persisted for sender {jid}", jid=sender_jid)
        except Exception as exc:
            logger.error("Failed to record security incident into database: {err}", err=exc)

    async def process_raw_envelope(
        self,
        envelope: AMQPMessageEnvelope,
        channel: aio_pika.abc.AbstractChannel | None = None,
        exchange: aio_pika.abc.AbstractExchange | None = None,
    ) -> dict[str, Any]:
        """Processes a single raw message envelope, transcribing and filtering."""
        payload = envelope.payload
        sender_jid = payload.get("sender_jid", "unknown")
        text_content = payload.get("text") or ""
        audio_base64 = payload.get("audio_base64")
        media_type = payload.get("media_type")

        # 1. Audio transcription if voice note
        if (audio_base64 or media_type in ("audio", "voice")) and audio_base64:
            try:
                transcription = await self.whisper_client.transcribe_base64(audio_base64)
                text_content = transcription.text
                payload["text"] = text_content
                payload["transcribed"] = True
                payload["duration_seconds"] = transcription.duration_seconds
            except Exception as exc:
                logger.error("Audio transcription failed for message {mid}: {err}", mid=envelope.message_id, err=exc)
                text_content = "[Áudio inaudível ou com falha de transcrição]"

        # 2. Safety & prompt injection inspection
        decision = await self.llama_guard_client.inspect(text_content)

        if decision.is_safe:
            # Clean message -> publish to whatsapp.inbound
            logger.info("Message {mid} passed guardrail. Routing to whatsapp.inbound.", mid=envelope.message_id)
            enriched_payload = {
                **payload,
                "guardrail_score": decision.risk_score,
                "inspected_at": datetime.now(timezone.utc).isoformat(),
            }
            inbound_envelope = AMQPMessageEnvelope(
                message_id=uuid.uuid4(),
                correlation_id=envelope.correlation_id,
                from_service="guardrail-gateway",
                to_service="engine-core",
                timestamp=datetime.now(timezone.utc),
                payload=enriched_payload,
            )

            if exchange:
                amqp_msg = aio_pika.Message(
                    body=inbound_envelope.model_dump_json().encode(),
                    content_type="application/json",
                    correlation_id=str(envelope.correlation_id),
                )
                await exchange.publish(amqp_msg, routing_key="whatsapp.inbound")

            return {
                "status": "forwarded",
                "routing_key": "whatsapp.inbound",
                "envelope": inbound_envelope,
            }
        else:
            # Threat detected -> Silent drop, record incident, alert telegram
            logger.warning(
                "Threat detected from {jid}: category={cat}, score={score}. Dropping silently.",
                jid=sender_jid,
                cat=decision.threat_category,
                score=decision.risk_score,
            )

            await self.record_security_incident(
                sender_jid=sender_jid,
                raw_message=text_content,
                threat_category=decision.threat_category or "unspecified",
                risk_score=decision.risk_score,
                action_taken="silent_drop",
            )

            alert_payload = {
                "level": "CRITICAL",
                "title": "Ataque ou Injeção de Prompt Detectada",
                "message": (
                    f"Remetente: {sender_jid}\n"
                    f"Categoria: {decision.threat_category}\n"
                    f"Score: {decision.risk_score:.2f}\n"
                    f"Conteúdo: {text_content[:200]}"
                ),
                "threat_category": decision.threat_category,
                "sender_jid": sender_jid,
            }
            alert_envelope = AMQPMessageEnvelope(
                message_id=uuid.uuid4(),
                correlation_id=envelope.correlation_id,
                from_service="guardrail-gateway",
                to_service="telegram-gateway",
                timestamp=datetime.now(timezone.utc),
                payload=alert_payload,
            )

            if exchange:
                amqp_msg = aio_pika.Message(
                    body=alert_envelope.model_dump_json().encode(),
                    content_type="application/json",
                    correlation_id=str(envelope.correlation_id),
                )
                await exchange.publish(amqp_msg, routing_key="telegram.alerts")

            return {
                "status": "blocked",
                "routing_key": "telegram.alerts",
                "incident_category": decision.threat_category,
                "envelope": alert_envelope,
            }
