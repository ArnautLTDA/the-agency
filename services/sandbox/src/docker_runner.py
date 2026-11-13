"""Docker-outside-of-Docker (DooD) ephemeral sandbox command execution (TC-127, TC-128, TC-129, TC-189, TC-190)."""

import asyncio
from pathlib import Path
import time
from typing import Any

import docker
from docker.errors import DockerException
from loguru import logger

from filesystem import resolve_workspace_path

MAX_TERMINAL_BUFFER_BYTES: int = 131072  # 128 KB
DEFAULT_DOCKER_IMAGE: str = "node:20-slim"


def truncate_buffer(data: str, max_bytes: int = MAX_TERMINAL_BUFFER_BYTES) -> str:
    """Truncates terminal output string to max_bytes with a visible security warning."""
    encoded = data.encode("utf-8")
    if len(encoded) <= max_bytes:
        return data

    truncated_bytes = encoded[:max_bytes]
    # Decode ignoring partial trailing UTF-8 sequence
    safe_str = truncated_bytes.decode("utf-8", errors="ignore")
    return safe_str + f"\n\n[WARNING: Terminal output truncated at {max_bytes} bytes for memory safety.]"


async def run_terminal_command(
    workspace_id: str,
    command: str,
    timeout_seconds: int = 60,
    docker_client: docker.DockerClient | None = None,
) -> dict[str, Any]:
    """Runs a command inside an ephemeral disposable Docker container with resource containment."""
    # Ensure workspace directory exists and canonical path is resolved
    workspace_path = resolve_workspace_path(workspace_id, ".").resolve()

    client = docker_client or docker.from_env()
    container = None
    start_time = time.time()

    # Ephemeral container configuration
    container_config = {
        "image": DEFAULT_DOCKER_IMAGE,
        "command": ["/bin/sh", "-c", command],
        "working_dir": "/workspace",
        "volumes": {
            str(workspace_path): {
                "bind": "/workspace",
                "mode": "rw",
            }
        },
        "network_mode": "none",  # Strict network isolation (TC-189)
        "mem_limit": "2g",       # Memory containment (TC-190)
        "nano_cpus": 1500000000, # 1.5 CPU quota
        "pids_limit": 100,
        "detach": True,
        "stdout": True,
        "stderr": True,
    }

    try:
        # Create and start ephemeral container asynchronously
        loop = asyncio.get_running_loop()
        container = await loop.run_in_executor(None, lambda: client.containers.create(**container_config))
        await loop.run_in_executor(None, container.start)

        # Await completion with strict timeout
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, container.wait),
                timeout=float(timeout_seconds),
            )
            exit_code = result.get("StatusCode", 1)
        except asyncio.TimeoutError:
            logger.warning(f"Command timed out after {timeout_seconds}s in container. Dispatching SIGKILL.")
            try:
                await loop.run_in_executor(None, lambda: container.kill(signal="SIGKILL"))
            except Exception as e:
                logger.error(f"Failed to kill container: {e}")
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout_seconds} seconds and was forcefully terminated.",
                "exit_code": 124,
                "duration_seconds": round(time.time() - start_time, 2),
                "is_timeout": True,
                "is_oom": False,
            }

        # Retrieve stdout and stderr logs
        raw_stdout = await loop.run_in_executor(
            None, lambda: container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        )
        raw_stderr = await loop.run_in_executor(
            None, lambda: container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        )

        stdout = truncate_buffer(raw_stdout)
        stderr = truncate_buffer(raw_stderr)
        is_oom = exit_code == 137

        if is_oom:
            stderr += "\n[ERROR: Process terminated due to Out Of Memory (OOM, exit code 137). Limit: 2GB]"

        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration_seconds": round(time.time() - start_time, 2),
            "is_timeout": False,
            "is_oom": is_oom,
        }

    except DockerException as exc:
        logger.error(f"Docker execution error: {exc}")
        return {
            "stdout": "",
            "stderr": f"Docker daemon execution error: {str(exc)}",
            "exit_code": 1,
            "duration_seconds": round(time.time() - start_time, 2),
            "is_timeout": False,
            "is_oom": False,
        }
    finally:
        if container is not None:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: container.remove(force=True))
            except Exception as e:
                logger.debug(f"Ephemeral container cleanup notice: {e}")
