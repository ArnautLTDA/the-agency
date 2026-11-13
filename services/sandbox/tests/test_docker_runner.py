"""Unit tests for Docker DooD runner and container limits (TC-127, TC-128, TC-129, TC-150, TC-189, TC-190)."""

from unittest.mock import MagicMock
import pytest

from docker_runner import (
    MAX_TERMINAL_BUFFER_BYTES,
    run_terminal_command,
    truncate_buffer,
)


def test_truncate_buffer_limits_output():
    """TC-128: Verifies terminal output is truncated at 128 KB with a warning notice."""
    oversized = "a" * (MAX_TERMINAL_BUFFER_BYTES + 500)
    result = truncate_buffer(oversized, max_bytes=MAX_TERMINAL_BUFFER_BYTES)
    assert len(result.encode("utf-8")) > MAX_TERMINAL_BUFFER_BYTES  # contains notice
    assert "[WARNING: Terminal output truncated" in result

    short_str = "normal output"
    assert truncate_buffer(short_str) == short_str


@pytest.mark.asyncio
async def test_run_terminal_command_parameters_and_isolation():
    """TC-127, TC-150 & TC-189: Verifies Docker container creation params: no network, 2GB RAM, 1.5 CPUs."""
    mock_docker = MagicMock()
    mock_container = MagicMock()

    mock_docker.containers.create.return_value = mock_container
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.side_effect = [b"Test Output\n", b""]

    res = await run_terminal_command(
        workspace_id="test_ws",
        command="npm test",
        docker_client=mock_docker,
    )

    assert res["exit_code"] == 0
    assert "Test Output" in res["stdout"]

    # Verify container creation arguments
    _, kwargs = mock_docker.containers.create.call_args
    assert kwargs["network_mode"] == "none", "Network mode must be 'none' for security isolation (TC-189)"
    assert kwargs["mem_limit"] == "2g", "Memory limit must be strictly capped at 2GB (TC-190)"
    assert kwargs["nano_cpus"] == 1500000000, "CPU quota must be capped at 1.5 CPUs"
    assert kwargs["working_dir"] == "/workspace"

    # Verify ephemeral container cleanup
    mock_container.remove.assert_called_once_with(force=True)


@pytest.mark.asyncio
async def test_run_terminal_command_oom_detection():
    """TC-190: Verifies exit code 137 is identified as Out Of Memory (OOM)."""
    mock_docker = MagicMock()
    mock_container = MagicMock()

    mock_docker.containers.create.return_value = mock_container
    mock_container.wait.return_value = {"StatusCode": 137}
    mock_container.logs.side_effect = [b"", b"Killed\n"]

    res = await run_terminal_command(
        workspace_id="test_ws",
        command="node leak.js",
        docker_client=mock_docker,
    )

    assert res["exit_code"] == 137
    assert res["is_oom"] is True
    assert "Out Of Memory" in res["stderr"]


@pytest.mark.asyncio
async def test_run_terminal_command_timeout_kills_container():
    """TC-129: Verifies command exceeding timeout_seconds triggers SIGKILL."""
    mock_docker = MagicMock()
    mock_container = MagicMock()

    mock_docker.containers.create.return_value = mock_container
    # Simulate wait blocking longer than timeout
    import time
    def slow_wait():
        time.sleep(0.5)
        return {"StatusCode": 0}

    mock_container.wait.side_effect = slow_wait

    res = await run_terminal_command(
        workspace_id="test_ws",
        command="sleep 60",
        timeout_seconds=0.1,  # Short timeout for test
        docker_client=mock_docker,
    )

    assert res["is_timeout"] is True
    assert res["exit_code"] == 124
    assert "timed out" in res["stderr"]
    mock_container.kill.assert_called_once_with(signal="SIGKILL")
