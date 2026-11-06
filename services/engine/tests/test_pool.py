"""Tests for Worker Pool Concurrency Semaphore and Queueing (TC-036)."""

import asyncio
import uuid
import pytest

from src.services.pool import AgentPool


@pytest.mark.asyncio
async def test_tc036_concurrency_semaphore_and_queue():
    """TC-036: 6 simultaneous requests with limit of 5. 5 run, 6th waits until a slot opens."""
    pool = AgentPool(max_concurrent=5)
    active_runs = []
    peak_concurrent = 0
    completed_runs = []

    async def simulated_task(task_id: int):
        nonlocal peak_concurrent
        active_runs.append(task_id)
        current_active = len(active_runs)
        if current_active > peak_concurrent:
            peak_concurrent = current_active
        # Simulate work
        await asyncio.sleep(0.05)
        active_runs.remove(task_id)
        completed_runs.append(task_id)

    # Dispatch 6 tasks concurrently
    run_ids = [uuid.uuid4() for _ in range(6)]
    tasks = [pool.submit(run_id=rid, coro=simulated_task(i)) for i, rid in enumerate(run_ids)]

    await asyncio.gather(*tasks)

    assert len(completed_runs) == 6
    assert peak_concurrent == 5  # strictly respected the semaphore limit of 5!
