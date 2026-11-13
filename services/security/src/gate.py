"""Security gate policy evaluation engine (TC-170, TC-211)."""

from pydantic import BaseModel, Field
from scanners.base import Finding, ScanReport, SeverityLevel


class GateDecision(BaseModel):
    """Result of evaluating security policies across all scan reports."""

    approved: bool
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    blocking_reasons: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


def evaluate_security_gate(reports: list[ScanReport]) -> GateDecision:
    """Evaluates security reports against the zero-critical/high gate policy."""
    all_findings: list[Finding] = []
    blocking_reasons: list[str] = []

    for report in reports:
        if report.error:
            blocking_reasons.append(f"Tool {report.tool} failed with execution error: {report.error}")

        all_findings.extend(report.findings)

        if not report.passed and not report.findings and not report.error:
            blocking_reasons.append(f"Tool {report.tool} reported gate failure")

    critical_count = 0
    high_count = 0
    medium_count = 0
    low_count = 0

    for f in all_findings:
        if f.severity == SeverityLevel.CRITICAL:
            critical_count += 1
            blocking_reasons.append(f"[{f.tool}] CRITICAL finding: {f.rule_id} - {f.description}")
        elif f.severity == SeverityLevel.HIGH:
            high_count += 1
            blocking_reasons.append(f"[{f.tool}] HIGH finding: {f.rule_id} - {f.description}")
        elif f.severity == SeverityLevel.MEDIUM:
            medium_count += 1
        elif f.severity in (SeverityLevel.LOW, SeverityLevel.INFO):
            low_count += 1

    approved = (critical_count == 0) and (high_count == 0) and (len(blocking_reasons) == 0)

    return GateDecision(
        approved=approved,
        total_findings=len(all_findings),
        critical_count=critical_count,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        blocking_reasons=blocking_reasons,
        findings=all_findings,
    )
