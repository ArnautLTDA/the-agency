"""Sandbox Drivers for isolated terminal execution with buffer cut and timeout (TC-031 to TC-035)."""

import os
import shutil
import signal
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from loguru import logger

from src.config import get_settings


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


def truncate_buffer(output: str, max_bytes: int = 131072) -> str:
    """Deterministically truncates output if exceeding max_bytes and appends warning footer."""
    encoded = output.encode("utf-8")
    if len(encoded) <= max_bytes:
        return output

    truncated_bytes = encoded[:max_bytes]
    truncated_str = truncated_bytes.decode("utf-8", errors="ignore")
    footer = "\n[AVISO: Saída truncada em 128 KB para preservar a memória do motor. Restante omitido.]"
    return truncated_str + footer


class BaseSandboxDriver(ABC):
    """Abstract base driver for executing commands in an isolated environment."""

    def __init__(self, max_buffer_bytes: int = 131072):
        self.max_buffer_bytes = max_buffer_bytes

    @abstractmethod
    def execute(self, command: str, cwd: Path, timeout: int = 60) -> CommandResult:
        """Executes the given command in cwd with timeout."""
        pass


class SubprocessSandboxDriver(BaseSandboxDriver):
    """Fallback local driver with sanitized environment, restricted cwd and process isolation."""

    def execute(self, command: str, cwd: Path, timeout: int = 60) -> CommandResult:
        sanitized_env = dict(os.environ)
        for sensitive_key in ["GEMINI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY"]:
            sanitized_env.pop(sensitive_key, None)

        proc = None
        try:
            # Use os.setsid to create a new process group so killpg terminates all child processes
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=sanitized_env,
                preexec_fn=os.setsid,
            )

            stdout_data, stderr_data = proc.communicate(timeout=timeout)
            exit_code = proc.returncode

            return CommandResult(
                stdout=truncate_buffer(stdout_data or "", self.max_buffer_bytes),
                stderr=truncate_buffer(stderr_data or "", self.max_buffer_bytes),
                exit_code=exit_code,
                timed_out=False,
            )
        except subprocess.TimeoutExpired:
            if proc is not None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout_data, stderr_data = proc.communicate()
            else:
                stdout_data, stderr_data = "", ""

            return CommandResult(
                stdout=truncate_buffer(stdout_data or "", self.max_buffer_bytes),
                stderr=truncate_buffer(
                    (stderr_data or "") + f"\nCommand timed out after {timeout} seconds.",
                    self.max_buffer_bytes,
                ),
                exit_code=124,
                timed_out=True,
            )
        except Exception as exc:
            return CommandResult(
                stdout="",
                stderr=f"Execution error: {exc}",
                exit_code=1,
                timed_out=False,
            )


class DockerSandboxDriver(BaseSandboxDriver):
    """Industry-standard disposable Docker container sandbox (Devin / OpenHands style)."""

    def __init__(
        self,
        image: str | None = None,
        max_buffer_bytes: int = 131072,
        memory_limit: str = "2g",
        cpus_limit: float = 1.5,
        pids_limit: int = 100,
        user: str = "node",
    ):
        super().__init__(max_buffer_bytes=max_buffer_bytes)
        settings = get_settings()
        self.image = image or settings.DOCKER_IMAGE
        self.memory_limit = memory_limit or settings.DOCKER_MEMORY_LIMIT
        self.cpus_limit = cpus_limit or settings.DOCKER_CPUS_LIMIT
        self.pids_limit = pids_limit or settings.DOCKER_PIDS_LIMIT
        self.user = user

    def is_available(self) -> bool:
        """Checks if docker CLI is available and docker daemon is reachable."""
        if not shutil.which("docker"):
            return False
        try:
            res = subprocess.run(
                ["docker", "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return res.returncode == 0
        except Exception:
            return False

    def execute(self, command: str, cwd: Path, timeout: int = 60) -> CommandResult:
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            f"--memory={self.memory_limit}",
            f"--cpus={self.cpus_limit}",
            f"--pids-limit={self.pids_limit}",
            "--security-opt=no-new-privileges:true",
            f"--user={self.user}",
            "-v",
            f"{cwd.resolve()}:/workspace",
            "-w",
            "/workspace",
            self.image,
            "bash",
            "-c",
            command,
        ]

        proc = None
        try:
            proc = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid,
            )
            stdout_data, stderr_data = proc.communicate(timeout=timeout)
            return CommandResult(
                stdout=truncate_buffer(stdout_data or "", self.max_buffer_bytes),
                stderr=truncate_buffer(stderr_data or "", self.max_buffer_bytes),
                exit_code=proc.returncode,
                timed_out=False,
            )
        except subprocess.TimeoutExpired:
            if proc is not None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout_data, stderr_data = proc.communicate()
            else:
                stdout_data, stderr_data = "", ""

            return CommandResult(
                stdout=truncate_buffer(stdout_data or "", self.max_buffer_bytes),
                stderr=truncate_buffer(
                    (stderr_data or "") + f"\nCommand timed out after {timeout} seconds.",
                    self.max_buffer_bytes,
                ),
                exit_code=124,
                timed_out=True,
            )
        except Exception as exc:
            return CommandResult(
                stdout="",
                stderr=f"Docker execution failure: {exc}",
                exit_code=1,
                timed_out=False,
            )


def get_sandbox_driver() -> BaseSandboxDriver:
    """Returns the primary DockerSandboxDriver if docker is active, or Subprocess fallback."""
    docker_driver = DockerSandboxDriver()
    if docker_driver.is_available():
        return docker_driver
    logger.warning("Docker daemon is not available; falling back to SubprocessSandboxDriver.")
    return SubprocessSandboxDriver()
