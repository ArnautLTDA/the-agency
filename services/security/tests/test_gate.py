"""Tests for Security Gate policy evaluation (TC-170, TC-211)."""

from gate import evaluate_security_gate
from scanners.base import Finding, ScanReport, SeverityLevel


def test_evaluate_security_gate_all_clean_tc170():
    """TC-170: All scans pass with zero high/critical findings -> Gate APPROVED."""
    reports = [
        ScanReport(tool="gitleaks", passed=True, findings=[]),
        ScanReport(tool="semgrep", passed=True, findings=[]),
        ScanReport(tool="trivy", passed=True, findings=[]),
        ScanReport(tool="sonarqube", passed=True, findings=[]),
        ScanReport(tool="nuclei", passed=True, findings=[]),
    ]

    decision = evaluate_security_gate(reports)
    assert decision.approved
    assert decision.total_findings == 0
    assert decision.critical_count == 0
    assert decision.high_count == 0
    assert len(decision.blocking_reasons) == 0


def test_evaluate_security_gate_allows_medium_and_low():
    """Security gate allows medium and low findings without blocking deployment."""
    reports = [
        ScanReport(
            tool="semgrep",
            passed=True,
            findings=[
                Finding(
                    rule_id="missing-security-header",
                    description="Minor header recommendation",
                    severity=SeverityLevel.LOW,
                    tool="semgrep",
                ),
                Finding(
                    rule_id="weak-hash-md5",
                    description="MD5 used for non-cryptographic checksum",
                    severity=SeverityLevel.MEDIUM,
                    tool="semgrep",
                ),
            ],
        )
    ]

    decision = evaluate_security_gate(reports)
    assert decision.approved
    assert decision.total_findings == 2
    assert decision.medium_count == 1
    assert decision.low_count == 1
    assert len(decision.blocking_reasons) == 0


def test_evaluate_security_gate_blocks_critical_and_high_tc211():
    """TC-211: Any CRITICAL or HIGH finding triggers deployment block with full reasons."""
    reports = [
        ScanReport(
            tool="gitleaks",
            passed=False,
            findings=[
                Finding(
                    rule_id="AWS_KEY",
                    description="Leaked AWS token",
                    severity=SeverityLevel.CRITICAL,
                    tool="gitleaks",
                )
            ],
        ),
        ScanReport(
            tool="semgrep",
            passed=False,
            findings=[
                Finding(
                    rule_id="SQL_INJECTION",
                    description="SQL injection in login endpoint",
                    severity=SeverityLevel.HIGH,
                    tool="semgrep",
                )
            ],
        ),
    ]

    decision = evaluate_security_gate(reports)
    assert not decision.approved
    assert decision.critical_count == 1
    assert decision.high_count == 1
    assert len(decision.blocking_reasons) >= 2
    assert any("CRITICAL" in reason for reason in decision.blocking_reasons)
    assert any("HIGH" in reason for reason in decision.blocking_reasons)


def test_evaluate_security_gate_blocks_on_tool_error():
    """If a security tool fails with execution error, gate is blocked."""
    reports = [
        ScanReport(
            tool="sonarqube",
            passed=False,
            error="Connection refused: http://localhost:9000",
        )
    ]

    decision = evaluate_security_gate(reports)
    assert not decision.approved
    assert any("failed with execution error" in r for r in decision.blocking_reasons)
