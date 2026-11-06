"""Tests for SSE Event Broker and Stream Resilience (TC-018, TC-019)."""

import asyncio
import uuid
import pytest

from src.api.sse import SSEBroker


@pytest.mark.asyncio
async def test_tc018_sse_streaming_typed_events():
    """TC-018: Clients receive typed events matching run_id filter."""
    broker = SSEBroker()
    run_id = uuid.uuid4()
    received_events = []

    async def client_listener():
        async for event in broker.subscribe(run_id=run_id):
            received_events.append(event)
            if event.event == "task_completed":
                break

    listener_task = asyncio.create_task(client_listener())
    await asyncio.sleep(0.01)  # Let subscriber register

    # Publish events
    await broker.publish(run_id=run_id, event_type="thought", data={"thought": "Thinking..."})
    await broker.publish(run_id=run_id, event_type="tool_call", data={"tool": "read_file"})
    await broker.publish(run_id=run_id, event_type="task_completed", data={"result": "Done"})

    await asyncio.wait_for(listener_task, timeout=2.0)

    assert len(received_events) == 3
    assert received_events[0].event == "thought"
    assert received_events[1].event == "tool_call"
    assert received_events[2].event == "task_completed"


@pytest.mark.asyncio
async def test_tc019_sse_abrupt_disconnect():
    """TC-019: Sudden client disconnection is handled gracefully without breaking server."""
    broker = SSEBroker()
    run_id = uuid.uuid4()

    async def faulty_client():
        async for event in broker.subscribe(run_id=run_id):
            # Simulate sudden socket drop
            raise ConnectionResetError("Client abruptly disconnected socket")

    client_task = asyncio.create_task(faulty_client())
    await asyncio.sleep(0.01)

    # Publishing to a subscriber that crashes with ConnectionResetError should not raise in publish
    try:
        await broker.publish(run_id=run_id, event_type="thought", data={"thought": "Testing disconnect"})
    except ConnectionResetError:
        pytest.fail("Broker allowed ConnectionResetError to escape during publish.")

    # Await client task completion so generator finally block cleans up
    await asyncio.gather(client_task, return_exceptions=True)

    # Subscriber queue is cleaned up
    assert broker.subscriber_count(run_id) == 0
