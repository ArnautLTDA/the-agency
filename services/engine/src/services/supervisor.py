"""Supervisor Service for Fail-Fast Resilience and Autonomous Recovery (TC-147, TC-148)."""

import asyncio
from enum import Enum
import os
import time
from typing import Any, Callable, Coroutine
import httpx
from loguru import logger

from agency_common.amqp import (
    AMQPMessageEnvelope,
    TOPIC_EXCHANGE_NAME,
)
from agency_common.auth import HEADER_AGENCY_KEY, get_agency_secret_key
from src.services.queue import QueueService, get_queue_service


class EngineOperationalState(str, Enum):
    """Operational states for The Agency Engine runtime."""

    OPERACIONAL = "OPERACIONAL"
    PAUSA_EMERGENCIAL = "PAUSA_EMERGENCIAL"


DEFAULT_VITAL_GATEWAYS: dict[str, str] = {
    "whatsapp": os.environ.get("WHATSAPP_GATEWAY_URL", "http://127.0.0.1:3005/api/v1/session/status"),
    "payment": os.environ.get("PAYMENT_GATEWAY_URL", "http://127.0.0.1:3006/api/v1/health"),
    "guardrail": os.environ.get("GUARDRAIL_GATEWAY_URL", "http://127.0.0.1:3007/api/v1/health"),
}


class VitalGatewayStatus:
    """Read-only data holder for single gateway health verification."""

    def __init__(
        self,
        name: str,
        url: str,
        is_healthy: bool,
        error: str | None = None,
        response_time_ms: float = 0.0,
    ) -> None:
        self.name = name
        self.url = url
        self.is_healthy = is_healthy
        self.error = error
        self.response_time_ms = response_time_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "is_healthy": self.is_healthy,
            "error": self.error,
            "response_time_ms": round(self.response_time_ms, 2),
        }


class SupervisorService:
    """Supervises vital microservice gateways with fail-fast pause and autonomous recovery."""

    def __init__(
        self,
        vital_gateways: dict[str, str] | None = None,
        poll_interval_seconds: float = 5.0,
        queue_service: QueueService | None = None,
        http_client: httpx.AsyncClient | None = None,
        alert_callback: Callable[[str, str, dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self.vital_gateways = dict(vital_gateways or DEFAULT_VITAL_GATEWAYS)
        self.poll_interval_seconds = poll_interval_seconds
        self.queue_service = queue_service
        self.http_client = http_client
        self.alert_callback = alert_callback

        self._state: EngineOperationalState = EngineOperationalState.OPERACIONAL
        self._manually_paused: bool = False
        self._last_incident_reason: str | None = None
        self._last_check_results: dict[str, VitalGatewayStatus] = {}
        self._background_task: asyncio.Task | None = None
        self._is_running: bool = False

    @property
    def state(self) -> EngineOperationalState:
        return self._state

    def is_paused(self) -> bool:
        return self._state == EngineOperationalState.PAUSA_EMERGENCIAL

    def get_last_results(self) -> dict[str, dict[str, Any]]:
        return {k: v.to_dict() for k, v in self._last_check_results.items()}

    async def _check_single_gateway(
        self,
        client: httpx.AsyncClient,
        name: str,
        url: str,
        headers: dict[str, str],
    ) -> VitalGatewayStatus:
        start_time = time.perf_counter()
        try:
            resp = await client.get(url, headers=headers)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            if resp.status_code == 200:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                # If json reports status == "unhealthy" or "error", mark unhealthy
                status_field = str(data.get("status", "healthy")).lower()
                if status_field in {"unhealthy", "error", "banned", "down"}:
                    return VitalGatewayStatus(
                        name=name,
                        url=url,
                        is_healthy=False,
                        error=f"Unhealthy status returned: {status_field}",
                        response_time_ms=elapsed_ms,
                    )
                return VitalGatewayStatus(
                    name=name,
                    url=url,
                    is_healthy=True,
                    response_time_ms=elapsed_ms,
                )
            else:
                return VitalGatewayStatus(
                    name=name,
                    url=url,
                    is_healthy=False,
                    error=f"HTTP {resp.status_code}",
                    response_time_ms=elapsed_ms,
                )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return VitalGatewayStatus(
                name=name,
                url=url,
                is_healthy=False,
                error=str(exc),
                response_time_ms=elapsed_ms,
            )

    async def check_vital_gateways(self) -> dict[str, VitalGatewayStatus]:
        """Probes all vital gateways concurrently."""
        headers = {HEADER_AGENCY_KEY: get_agency_secret_key()}
        results: dict[str, VitalGatewayStatus] = {}

        if self.http_client is not None:
            tasks = [
                self._check_single_gateway(self.http_client, name, url, headers)
                for name, url in self.vital_gateways.items()
            ]
            completed = await asyncio.gather(*tasks)
            for status in completed:
                results[status.name] = status
        else:
            async with httpx.AsyncClient(timeout=2.0) as client:
                tasks = [
                    self._check_single_gateway(client, name, url, headers)
                    for name, url in self.vital_gateways.items()
                ]
                completed = await asyncio.gather(*tasks)
                for status in completed:
                    results[status.name] = status

        self._last_check_results = results
        return results

    async def _dispatch_telegram_alert(
        self,
        level: str,
        title: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Dispatches an alert to Telegram via AMQP or registered callback."""
        payload = {
            "level": level,
            "title": title,
            "message": message,
            "details": details or {},
        }

        # 1. Callback hook (if provided)
        if self.alert_callback is not None:
            try:
                await self.alert_callback(level, title, payload)
            except Exception as err:
                logger.error(f"Error executing supervisor alert callback: {err}")

        # 2. AMQP channel dispatch to telegram.alerts queue
        qs = self.queue_service or get_queue_service()
        if qs is not None and qs.is_connected and qs.channel is not None:
            try:
                envelope = AMQPMessageEnvelope(
                    from_service="engine-core",
                    to_service="telegram-gateway",
                    payload=payload,
                )
                topic_exchange = await qs.channel.get_exchange(TOPIC_EXCHANGE_NAME)
                import aio_pika
                msg = aio_pika.Message(
                    body=envelope.to_bytes(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    correlation_id=envelope.correlation_id,
                )
                routing_key = "telegram.alert.emergency" if level == "CRITICAL" else "telegram.alert.info"
                await topic_exchange.publish(msg, routing_key=routing_key)
                logger.info(f"Supervisor alert dispatched to AMQP exchange {TOPIC_EXCHANGE_NAME} with key {routing_key}")
            except Exception as exc:
                logger.warning(f"Could not publish supervisor alert to RabbitMQ: {exc}")

    def _freeze_outbound_queues(self) -> None:
        """Freezes active prospecting while retaining inbound message buffer (TC-147)."""
        qs = self.queue_service or get_queue_service()
        if qs is not None and hasattr(qs, "freeze_outbound"):
            qs.freeze_outbound()
        logger.warning("Outbound prospecting queues FROZEN by Supervisor.")

    def _unfreeze_outbound_queues(self) -> None:
        """Resumes active prospecting queues upon recovery (TC-148)."""
        qs = self.queue_service or get_queue_service()
        if qs is not None and hasattr(qs, "unfreeze_outbound"):
            qs.unfreeze_outbound()
        logger.info("Outbound prospecting queues RESUMED by Supervisor.")

    async def step(self) -> EngineOperationalState:
        """Executes a single monitoring cycle and transitions state if necessary."""
        results = await self.check_vital_gateways()
        failed_gateways = [s for s in results.values() if not s.is_healthy]

        if failed_gateways:
            failure_reasons = [f"{g.name} ({g.error})" for g in failed_gateways]
            combined_reason = ", ".join(failure_reasons)

            if self._state == EngineOperationalState.OPERACIONAL:
                # TC-147: Fail-Fast transition to PAUSA_EMERGENCIAL
                logger.critical(
                    f"Vital gateway check failed: {combined_reason}. Transitioning to PAUSA_EMERGENCIAL."
                )
                self._state = EngineOperationalState.PAUSA_EMERGENCIAL
                self._last_incident_reason = combined_reason
                self._freeze_outbound_queues()

                await self._dispatch_telegram_alert(
                    level="CRITICAL",
                    title="Pausa Emergencial Ativada",
                    message=(
                        f"A esteira operacional entrou em PAUSA_EMERGENCIAL.\n"
                        f"Gateways afetados: {combined_reason}.\n"
                        f"Abordagens ativas congeladas. Inbound protegido em buffer RabbitMQ."
                    ),
                    details={"failed_gateways": [g.to_dict() for g in failed_gateways]},
                )
            else:
                self._last_incident_reason = combined_reason

        else:
            # All vital gateways are healthy
            if self._state == EngineOperationalState.PAUSA_EMERGENCIAL and not self._manually_paused:
                # TC-148: Autonomous recovery back to OPERACIONAL
                logger.info(
                    "All vital gateways restored to healthy state. Resuming OPERACIONAL mode."
                )
                self._state = EngineOperationalState.OPERACIONAL
                self._last_incident_reason = None
                self._unfreeze_outbound_queues()

                await self._dispatch_telegram_alert(
                    level="INFO",
                    title="Esteira Normalizada",
                    message=(
                        "Todos os gateways vitais foram recuperados com sucesso.\n"
                        "Estado operacional retomado automaticamente. Filas comerciais ativas."
                    ),
                    details={"gateways": [g.to_dict() for g in results.values()]},
                )

        return self._state

    async def pause_manually(self, reason: str = "Pausa solicitada pelo administrador") -> None:
        """Manually suspends active outreach and puts engine into emergency pause."""
        logger.warning(f"Manual pause requested: {reason}")
        self._manually_paused = True
        self._state = EngineOperationalState.PAUSA_EMERGENCIAL
        self._last_incident_reason = reason
        self._freeze_outbound_queues()

        await self._dispatch_telegram_alert(
            level="WARNING",
            title="Pausa Manual Acionada",
            message=f"Operacao da esteira pausada manualmente por Joao: {reason}.",
            details={"manual": True, "reason": reason},
        )

    async def resume_manually(self) -> bool:
        """Manually resumes operations if vital gateways are healthy."""
        logger.info("Manual resume requested by administrator.")
        results = await self.check_vital_gateways()
        failed = [s for s in results.values() if not s.is_healthy]

        if failed:
            failed_str = ", ".join(f"{g.name}: {g.error}" for g in failed)
            logger.error(
                f"Cannot resume operations manually: vital gateways still down ({failed_str})"
            )
            return False

        self._manually_paused = False
        self._state = EngineOperationalState.OPERACIONAL
        self._last_incident_reason = None
        self._unfreeze_outbound_queues()

        await self._dispatch_telegram_alert(
            level="INFO",
            title="Operacao Retomada",
            message="Esteira operacional retomada com sucesso apos confirmacao de saude dos gateways.",
            details={"manual": True},
        )
        return True

    async def start(self) -> None:
        """Starts background periodic polling loop."""
        if self._is_running:
            return
        self._is_running = True

        async def _loop():
            logger.info(
                f"Supervisor monitoring loop started with interval of {self.poll_interval_seconds}s."
            )
            while self._is_running:
                try:
                    await self.step()
                except Exception as exc:
                    logger.error(f"Unexpected error in supervisor step: {exc}")
                await asyncio.sleep(self.poll_interval_seconds)

        self._background_task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        """Stops background monitoring cleanly."""
        self._is_running = False
        if self._background_task is not None:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
        logger.info("Supervisor monitoring loop stopped.")

    def get_status_report(self) -> dict[str, Any]:
        """Consolidates complete supervisor state and gateway telemetry."""
        return {
            "state": self._state.value,
            "is_paused": self.is_paused(),
            "manually_paused": self._manually_paused,
            "last_incident_reason": self._last_incident_reason,
            "poll_interval_seconds": self.poll_interval_seconds,
            "vital_gateways": self.get_last_results(),
        }


# Global singleton supervisor instance
_supervisor_instance: SupervisorService | None = None


def get_supervisor() -> SupervisorService:
    global _supervisor_instance
    if _supervisor_instance is None:
        _supervisor_instance = SupervisorService()
    return _supervisor_instance


def set_supervisor(supervisor: SupervisorService | None) -> None:
    global _supervisor_instance
    _supervisor_instance = supervisor
