"""Tests for Sandbox Terminal Execution, Buffer Cut and Timeout (TC-031 to TC-035)."""

import time
from pathlib import Path

import pytest

from src.runner.sandbox import DockerSandboxDriver, SubprocessSandboxDriver, get_sandbox_driver


def test_tc031_subprocess_command_success(temp_workspace: Path):
    """TC-031: Executes simple shell command successfully with exit code 0."""
    driver = SubprocessSandboxDriver()
    result = driver.execute(command="python3 --version", cwd=temp_workspace)
    assert result.exit_code == 0
    assert "Python" in result.stdout
    assert result.timed_out is False


def test_tc032_command_with_error(temp_workspace: Path):
    """TC-032: Invalid command returns non-zero exit code and stderr for LLM reasoning."""
    driver = SubprocessSandboxDriver()
    result = driver.execute(command="python3 -c 'import non_existent_pkg'", cwd=temp_workspace)
    assert result.exit_code != 0
    assert "ModuleNotFoundError" in result.stderr or "non_existent_pkg" in result.stderr


def test_tc033_buffer_truncation_128kb(temp_workspace: Path):
    """TC-033: Output exceeding 128 KB (131072 bytes) is truncated deterministically with footer warning."""
    driver = SubprocessSandboxDriver(max_buffer_bytes=131072)
    # Generate ~200 KB of stdout
    command = "python3 -c 'print(\"A\" * 200000)'"
    result = driver.execute(command=command, cwd=temp_workspace)

    assert len(result.stdout.encode("utf-8")) <= 131072 + 200  # including footer warning
    assert "[AVISO: Saída truncada em 128 KB" in result.stdout


def test_tc034_timeout_enforcement(temp_workspace: Path):
    """TC-034: Command exceeding timeout limit is terminated with SIGKILL without hanging."""
    driver = SubprocessSandboxDriver()
    start_time = time.time()
    result = driver.execute(command="sleep 10", cwd=temp_workspace, timeout=1)
    duration = time.time() - start_time

    assert result.timed_out is True
    assert result.exit_code != 0
    assert duration < 3.0  # Killed around 1s
    assert "timed out" in result.stderr.lower()


def test_tc031_tc035_docker_sandbox_execution(temp_workspace: Path):
    """TC-031 & TC-035: Docker container runs command inside mounted workspace and isolates host."""
    driver = DockerSandboxDriver()
    if not driver.is_available():
        pytest.skip("Docker daemon not available in this test environment")

    # Write a test file in the workspace
    (temp_workspace / "hello.txt").write_text("from_host", encoding="utf-8")

    # Execute in docker
    result = driver.execute(command="cat /workspace/hello.txt", cwd=temp_workspace)
    assert result.exit_code == 0
    assert "from_host" in result.stdout

    # TC-035: Check host isolation (cannot read host's /etc/shadow or access host files)
    sec_check = driver.execute(command="cat /etc/shadow", cwd=temp_workspace)
    assert sec_check.exit_code != 0
    assert "permission denied" in sec_check.stderr.lower() or "no such file" in sec_check.stderr.lower()
