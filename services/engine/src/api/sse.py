"""Server-Sent Events (SSE) Manager with per-run and global pub/sub (TC-018, TC-019, SEC-022)."""

import asyncio
import json
import re
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from loguru import logger

from src.utils.security import mask_sensitive_data


@dataclass(frozen=True)
class SSEEvent:
    id: int
    event: str
    data: str

    def encode(self) -> str:
        """Formats the event according to W3C Server-Sent Events protocol with newline sanitization (SEC-022)."""
        clean_event = re.sub(r"[\r\n]+", "", self.event)
        return f"id: {self.id}\nevent: {clean_event}\ndata: {self.data}\n\n"


class SSEBroker:
    """In-memory pub/sub broker distributing lifecycle events to connected clients."""

    def __init__(self):
        self._subscribers: dict[uuid.UUID | None, list[asyncio.Queue[SSEEvent]]] = {}
        self._event_counter: int = 0
        self._lock = asyncio.Lock()

    def subscriber_count(self, run_id: uuid.UUID | None = None) -> int:
        return len(self._subscribers.get(run_id, []))

    async def publish(
        self,
        run_id: uuid.UUID,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Publishes an event to run-specific subscribers and global listeners with framing sanitization (SEC-022)."""
        self._event_counter += 1
        # SEC-022: Remove newline and carriage return characters from event_type
        sanitized_event_type = re.sub(r"[\r\n]+", "", event_type)

        # SEC-007: Mask sensitive values
        sanitized_data = {}
        for k, v in data.items():
            if isinstance(v, str):
                sanitized_data[k] = mask_sensitive_data(v)
            else:
                sanitized_data[k] = v

        event = SSEEvent(
            id=self._event_counter,
            event=sanitized_event_type,
            data=json.dumps(sanitized_data),
        )

        async with self._lock:
            # Deliver to run-specific queues
            target_queues = list(self._subscribers.get(run_id, []))
            # Also deliver to global listeners (None key)
            target_queues.extend(self._subscribers.get(None, []))

        for queue in target_queues:
            try:
                queue.put_nowait(event)
            except Exception as exc:
                logger.debug(f"Failed to deliver SSE event to a queue: {exc}")

    async def subscribe(
        self,
        run_id: uuid.UUID | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Subscribes to events for a specific run_id or global feed, yielding SSE events."""
        queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=100)

        async with self._lock:
            if run_id not in self._subscribers:
                self._subscribers[run_id] = []
            self._subscribers[run_id].append(queue)

        try:
            while True:
                event = await queue.get()
                yield event
        except (ConnectionResetError, asyncio.CancelledError):
            logger.debug(f"SSE client disconnected for run_id={run_id}")
        finally:
            async with self._lock:
                if run_id in self._subscribers and queue in self._subscribers[run_id]:
                    self._subscribers[run_id].remove(queue)
                    if not self._subscribers[run_id]:
                        self._subscribers.pop(run_id, None)


# Global singleton instance
_sse_broker: SSEBroker | None = None


def get_sse_broker() -> SSEBroker:
    global _sse_broker
    if _sse_broker is None:
        _sse_broker = SSEBroker()
    return _sse_broker
