"""Tests for individual security scanners (TC-166, TC-167, TC-168, TC-169, TC-208, TC-209, TC-210)."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
import respx

from scanners.base import SeverityLevel, run_scanner_process
from scanners.gitleaks import scan_secrets
from scanners.nuclei import run_dast_scan
from scanners.semgrep import scan_sast_semgrep
from scanners.sonarqube import SonarQubeClient, run_sonarqube_scan
from scanners.trivy import scan_dependencies


@pytest.mark.asyncio
async def test_gitleaks_detects_secret_tc166(tmp_path: Path):
    """TC-166: Gitleaks scanner detects hardcoded credentials and reports CRITICAL severity."""
    secret_dir = tmp_path / "leaks"
    secret_dir.mkdir()
    secret_file = secret_dir / "config.py"
    secret_file.write_text('AWS_SECRET_KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8")

    report = await scan_secrets(str(secret_dir))
    assert not report.passed
    assert len(report.findings) > 0
    assert any(f.rule_id == "AWS_KEY" or "AWS" in f.rule_id for f in report.findings)
    assert any(f.severity == SeverityLevel.CRITICAL for f in report.findings)


@pytest.mark.asyncio
async def test_gitleaks_clean_code_tc209(tmp_path: Path):
    """TC-209: Gitleaks scanner passes cleanly on code with no hardcoded credentials."""
    clean_dir = tmp_path / "clean_repo"
    clean_dir.mkdir()
    (clean_dir / "app.py").write_text("import os\napi_key = os.getenv('API_KEY')\n", encoding="utf-8")

    report = await scan_secrets(str(clean_dir))
    assert report.passed
    assert len(report.findings) == 0


@pytest.mark.asyncio
async def test_semgrep_detects_injection_tc167(tmp_path: Path):
    """TC-167: Semgrep detects SQL Injection / Command Injection vulnerabilities."""
    vuln_dir = tmp_path / "sast_vuln"
    vuln_dir.mkdir()
    vuln_file = vuln_dir / "database.py"
    vuln_file.write_text(
        'def get_user(db, user_id):\n    return db.execute("SELECT * FROM users WHERE id = " + user_id)\n',
        encoding="utf-8",
    )

    report = await scan_sast_semgrep(str(vuln_dir))
    assert not report.passed
    assert len(report.findings) > 0
    assert any(f.rule_id == "SQL_INJECTION" or "SQL" in f.rule_id for f in report.findings)
    assert any(f.severity in (SeverityLevel.HIGH, SeverityLevel.CRITICAL) for f in report.findings)


@pytest.mark.asyncio
async def test_semgrep_clean_code(tmp_path: Path):
    """Semgrep passes when code uses parameterized queries."""
    clean_dir = tmp_path / "sast_clean"
    clean_dir.mkdir()
    clean_file = clean_dir / "database.py"
    clean_file.write_text(
        'def get_user(db, user_id):\n    return db.execute("SELECT * FROM users WHERE id = :id", {"id": user_id})\n',
        encoding="utf-8",
    )

    report = await scan_sast_semgrep(str(clean_dir))
    assert report.passed
    assert len(report.findings) == 0


@pytest.mark.asyncio
async def test_trivy_detects_vulnerable_dependency_tc168(tmp_path: Path):
    """TC-168: Trivy detects CVEs in outdated dependencies with HIGH/CRITICAL severity."""
    dep_dir = tmp_path / "deps"
    dep_dir.mkdir()
    req_file = dep_dir / "requirements.txt"
    req_file.write_text("urllib3==1.25.9\npyyaml==5.3.1\n", encoding="utf-8")

    report = await scan_dependencies(str(dep_dir))
    assert not report.passed
    assert len(report.findings) >= 2
    assert any("CVE-2021-33503" in f.rule_id for f in report.findings)
    assert any(f.severity in (SeverityLevel.HIGH, SeverityLevel.CRITICAL) for f in report.findings)


@pytest.mark.asyncio
async def test_trivy_clean_dependencies(tmp_path: Path):
    """Trivy passes cleanly when dependencies are up to date."""
    dep_dir = tmp_path / "deps_clean"
    dep_dir.mkdir()
    req_file = dep_dir / "requirements.txt"
    req_file.write_text("urllib3>=2.2.0\npyyaml>=6.0.2\n", encoding="utf-8")

    report = await scan_dependencies(str(dep_dir))
    assert report.passed
    assert len(report.findings) == 0


@pytest.mark.asyncio
async def test_nuclei_dast_probe_tc210():
    """TC-210: DAST probe identifies exposed sensitive endpoints like /.env."""
    with respx.mock(base_url="https://preview.agency.dev") as mock:
        mock.get("/").respond(200, headers={"X-Frame-Options": "DENY", "Content-Security-Policy": "default-src 'self'"})
        mock.get("/.env").respond(200, text="DATABASE_URL=postgres://user:pass@localhost/db")
        mock.get("/.git/HEAD").respond(404)

        report = await run_dast_scan("https://preview.agency.dev")
        assert not report.passed
        assert any("exposed-endpoint-env" in f.rule_id for f in report.findings)
        assert any(f.severity == SeverityLevel.CRITICAL for f in report.findings)


@pytest.mark.asyncio
async def test_sonarqube_quality_gate_passed_tc169():
    """TC-169: SonarQube Quality Gate OK results in passed scan report."""
    with respx.mock(base_url="http://localhost:9000") as mock:
        mock.get("/api/qualitygates/project_status").respond(
            200,
            json={
                "projectStatus": {
                    "status": "OK",
                    "conditions": [
                        {"metricKey": "coverage", "status": "OK", "actualValue": "85.2"},
                        {"metricKey": "bugs", "status": "OK", "actualValue": "0"},
                    ],
                }
            },
        )

        client = SonarQubeClient(base_url="http://localhost:9000", token="test")
        report = await run_sonarqube_scan("test-project", client=client)
        assert report.passed
        assert len(report.findings) == 0


@pytest.mark.asyncio
async def test_sonarqube_quality_gate_failed_tc169():
    """TC-169: SonarQube Quality Gate ERROR results in failed scan report with findings."""
    with respx.mock(base_url="http://localhost:9000") as mock:
        mock.get("/api/qualitygates/project_status").respond(
            200,
            json={
                "projectStatus": {
                    "status": "ERROR",
                    "conditions": [
                        {
                            "metricKey": "coverage",
                            "status": "ERROR",
                            "actualValue": "42.0",
                            "errorThreshold": "80",
                        }
                    ],
                }
            },
        )

        client = SonarQubeClient(base_url="http://localhost:9000", token="test")
        report = await run_sonarqube_scan("test-project", client=client)
        assert not report.passed
        assert len(report.findings) == 1
        assert "sonar-qg-coverage" in report.findings[0].rule_id


@pytest.mark.asyncio
async def test_sonarqube_service_unavailable_tc208():
    """TC-208: SonarQube service unavailable does not crash service, returns error report."""
    with respx.mock(base_url="http://localhost:9000") as mock:
        mock.get("/api/qualitygates/project_status").respond(503)

        client = SonarQubeClient(base_url="http://localhost:9000", token="test")
        report = await run_sonarqube_scan("test-project", client=client)
        assert not report.passed
        assert report.error is not None
        assert "503" in report.error


@pytest.mark.asyncio
async def test_run_scanner_process_timeout_and_process_guard():
    """Guards timeout and process signals ensuring PID/PGID > 1 (Rule 6)."""
    with patch("asyncio.create_subprocess_exec") as mock_exec, \
         patch("os.getpgid", return_value=9999) as mock_getpgid, \
         patch("os.killpg") as mock_killpg:

        mock_proc = MagicMock()
        mock_proc.pid = 9999  # Explicit valid PID > 1
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_proc.kill = MagicMock()
        mock_exec.return_value = mock_proc

        retcode, stdout, stderr = await run_scanner_process(["dummy-scanner"], timeout_seconds=0.01)

        assert retcode == 124
        assert "timed out" in stderr
        mock_killpg.assert_called_once()


@pytest.mark.asyncio
async def test_sonarqube_get_project_measures():
    """Verifies SonarQube measures retrieval."""
    with respx.mock(base_url="http://localhost:9000") as mock:
        mock.get("/api/measures/component").respond(
            200,
            json={"component": {"measures": [{"metric": "coverage", "value": "91.2"}]}},
        )
        client = SonarQubeClient(base_url="http://localhost:9000", token="test")
        data = await client.get_project_measures("my-project")
        assert "component" in data


@pytest.mark.asyncio
async def test_semgrep_cli_json_parser(tmp_path: Path):
    """Verifies parsing of standard Semgrep JSON output."""
    sample_dir = tmp_path / "semgrep_cli"
    sample_dir.mkdir()
    semgrep_output = (
        '{"results": [{"check_id": "owasp.injection", "path": "app.py", '
        '"start": {"line": 10}, "extra": {"severity": "ERROR", "message": "SQL Injection"}}]}'
    )

    with patch("scanners.semgrep.run_scanner_process", return_value=(0, semgrep_output, "")):
        report = await scan_sast_semgrep(str(sample_dir))
        assert not report.passed
        assert len(report.findings) == 1
        assert report.findings[0].severity == SeverityLevel.CRITICAL


@pytest.mark.asyncio
async def test_trivy_cli_json_parser(tmp_path: Path):
    """Verifies parsing of standard Trivy JSON output."""
    sample_dir = tmp_path / "trivy_cli"
    sample_dir.mkdir()
    trivy_output = (
        '{"Results": [{"Target": "package-lock.json", "Vulnerabilities": ['
        '{"VulnerabilityID": "CVE-2023-1234", "PkgName": "foo", "Severity": "HIGH", "Title": "Remote Execution"}'
        ']}]}'
    )

    with patch("scanners.trivy.run_scanner_process", return_value=(0, trivy_output, "")):
        report = await scan_dependencies(str(sample_dir))
        assert not report.passed
        assert len(report.findings) == 1
        assert report.findings[0].severity == SeverityLevel.HIGH
