"""Base models and safe process execution primitives for security scanners."""

import asyncio
from enum import Enum
import os
import signal
from typing import Sequence
from loguru import logger
from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    """Normalized vulnerability severity levels."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Finding(BaseModel):
    """Normalized vulnerability or secret finding."""

    rule_id: str
    description: str
    file_path: str = ""
    line_number: int | None = None
    severity: SeverityLevel = SeverityLevel.MEDIUM
    tool: str


class ScanReport(BaseModel):
    """Unified scan report returned by scanners."""

    tool: str
    passed: bool
    findings: list[Finding] = Field(default_factory=list)
    raw_output: str | None = None
    error: str | None = None


async def run_scanner_process(
    cmd: Sequence[str],
    timeout_seconds: float = 60.0,
) -> tuple[int, str, str]:
    """Safely runs an external scanner process with process group isolation and timeout."""
    logger.info("Executing scanner command: {cmd}", cmd=" ".join(cmd))
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_seconds,
        )
        return (
            proc.returncode if proc.returncode is not None else 1,
            stdout_bytes.decode("utf-8", errors="replace"),
            stderr_bytes.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        logger.warning("Scanner execution timed out after {timeout}s", timeout=timeout_seconds)
        if proc and isinstance(proc.pid, int) and proc.pid > 1:
            try:
                pgid = os.getpgid(proc.pid)
                if isinstance(pgid, int) and pgid > 1:
                    os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.kill()
                except (ProcessLookupError, PermissionError, OSError):
                    pass
        return (124, "", f"Scanner timed out after {timeout_seconds} seconds")
    except FileNotFoundError:
        return (127, "", f"Binary '{cmd[0]}' not found in PATH")
    except Exception as exc:
        logger.error("Scanner process execution error: {exc}", exc=exc)
        return (1, "", str(exc))
