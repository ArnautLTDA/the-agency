"""Tests for Sandbox Isolation, Fail-Closed Security and Container Hygiene (TC-050 to TC-054)."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import Settings
from src.runner.sandbox import DockerSandboxDriver, SubprocessSandboxDriver, get_sandbox_driver


def test_tc050_docker_network_none_isolation(temp_workspace: Path):
    """TC-050 / SEC-004: Docker sandbox command includes --network=none flag."""
    driver = DockerSandboxDriver()

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("stdout_ok", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        driver.execute(command="curl https://google.com", cwd=temp_workspace)

        assert mock_popen.called
        cmd_args = mock_popen.call_args[0][0]
        assert "--network=none" in cmd_args


def test_tc051_docker_security_caps_and_read_only(temp_workspace: Path):
    """TC-051 / SEC-004: Docker container drops caps, sets read-only root and mounts secure tmpfs."""
    driver = DockerSandboxDriver()

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("ok", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        driver.execute(command="whoami", cwd=temp_workspace)

        assert mock_popen.called
        cmd_args = mock_popen.call_args[0][0]
        assert "--cap-drop=ALL" in cmd_args
        assert "--read-only" in cmd_args
        assert "--tmpfs=/tmp:rw,noexec,nosuid,size=64m" in cmd_args
        assert "--security-opt=no-new-privileges:true" in cmd_args


def test_tc052_sandbox_fail_closed_when_docker_unavailable():
    """TC-052 / SEC-002: get_sandbox_driver raises RuntimeError when Docker is offline and fallback is false."""
    mock_settings = MagicMock()
    mock_settings.ALLOW_LOCAL_SUBPROCESS_DEV = False
    mock_settings.DOCKER_IMAGE = "node:20-slim"
    mock_settings.DOCKER_MEMORY_LIMIT = "2g"
    mock_settings.DOCKER_CPUS_LIMIT = 1.5
    mock_settings.DOCKER_PIDS_LIMIT = 100

    with patch("src.runner.sandbox.DockerSandboxDriver.is_available", return_value=False):
        with patch("src.runner.sandbox.get_settings", return_value=mock_settings):
            with pytest.raises(RuntimeError) as exc_info:
                get_sandbox_driver()
            assert "Fail-Closed" in str(exc_info.value)
            assert "Docker daemon is unreachable" in str(exc_info.value)


def test_tc053_sandbox_fallback_allowed_when_explicitly_configured():
    """TC-053 / SEC-002: get_sandbox_driver returns SubprocessSandboxDriver when ALLOW_LOCAL_SUBPROCESS_DEV is True."""
    mock_settings = MagicMock()
    mock_settings.ALLOW_LOCAL_SUBPROCESS_DEV = True
    mock_settings.DOCKER_IMAGE = "node:20-slim"
    mock_settings.DOCKER_MEMORY_LIMIT = "2g"
    mock_settings.DOCKER_CPUS_LIMIT = 1.5
    mock_settings.DOCKER_PIDS_LIMIT = 100

    with patch("src.runner.sandbox.DockerSandboxDriver.is_available", return_value=False):
        with patch("src.runner.sandbox.get_settings", return_value=mock_settings):
            driver = get_sandbox_driver()
            assert isinstance(driver, SubprocessSandboxDriver)


def test_tc054_deterministic_container_naming_and_zombie_cleanup(temp_workspace: Path):
    """TC-054 / SEC-018: Container uses deterministic naming agency-{run_id}-{timestamp} and issues docker kill on timeout."""
    driver = DockerSandboxDriver()
    run_id = "testrun-1234-abcd"

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="sleep", timeout=1),
            ("stdout_killed", "stderr_killed"),
        ]
        mock_popen.return_value = mock_proc

        with patch("subprocess.run") as mock_run, patch("os.killpg") as mock_killpg, patch("os.getpgid", return_value=99999):
            result = driver.execute(command="sleep 10", cwd=temp_workspace, timeout=1, run_id=run_id)

            assert result.timed_out is True
            # Verify deterministic name prefix was in docker command
            cmd_args = mock_popen.call_args[0][0]
            name_arg = next((arg for arg in cmd_args if arg.startswith("--name=agency-testrun-")), None)
            assert name_arg is not None

            # Verify docker kill and docker rm were called to destroy zombie container
            assert mock_run.called
            killed_cmds = [call_args[0][0] for call_args in mock_run.call_args_list]
            assert any(cmd[0:2] == ["docker", "kill"] for cmd in killed_cmds)
            assert any(cmd[0:2] == ["docker", "rm"] for cmd in killed_cmds)
