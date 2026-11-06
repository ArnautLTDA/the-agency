"""Worker Pool and Concurrency Semaphore Manager (TC-036)."""

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any
from loguru import logger

from src.config import get_settings


class AgentPool:
    """Manages concurrent agent executions with an async semaphore and ordered queuing."""

    def __init__(self, max_concurrent: int | None = None):
        settings = get_settings()
        self.max_concurrent = max_concurrent or settings.MAX_CONCURRENT_AGENTS
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._active_tasks: dict[uuid.UUID, asyncio.Task] = {}
        self._queued_count: int = 0

    @property
    def active_count(self) -> int:
        return len(self._active_tasks)

    @property
    def queued_count(self) -> int:
        return self._queued_count

    async def submit(
        self,
        run_id: uuid.UUID,
        coro: Coroutine[Any, Any, Any],
    ) -> Any:
        """Executes a coroutine under the concurrency semaphore, queueing if limit is reached."""
        self._queued_count += 1
        logger.info(
            f"Run {run_id} entered queue (Active: {self.active_count}/{self.max_concurrent}, Queued: {self._queued_count})"
        )

        async with self._semaphore:
            self._queued_count -= 1
            current_task = asyncio.current_task()
            if current_task:
                self._active_tasks[run_id] = current_task

            logger.info(f"Run {run_id} acquired semaphore slot. Executing...")
            try:
                return await coro
            finally:
                self._active_tasks.pop(run_id, None)
                logger.info(
                    f"Run {run_id} released semaphore slot. (Active: {self.active_count}/{self.max_concurrent})"
                )

    async def shutdown(self):
        """Cancels all active running tasks during server shutdown."""
        tasks = list(self._active_tasks.values())
        if tasks:
            logger.info(f"Shutting down pool, cancelling {len(tasks)} running tasks.")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


# Global singleton instance
_agent_pool: AgentPool | None = None


def get_agent_pool() -> AgentPool:
    global _agent_pool
    if _agent_pool is None:
        _agent_pool = AgentPool()
    return _agent_pool
