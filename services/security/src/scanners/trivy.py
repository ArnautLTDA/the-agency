"""Trivy dependency / SCA vulnerability scanner integration."""

import json
from pathlib import Path
import re
from loguru import logger

from config import settings
from scanners.base import Finding, ScanReport, SeverityLevel, run_scanner_process

_KNOWN_VULNERABLE_PACKAGES = [
    ("urllib3", r"urllib3\s*==\s*1\.25\.", "CVE-2021-33503", "urllib3 ReDoS vulnerability in authority parsing", SeverityLevel.HIGH),
    ("requests", r"requests\s*==\s*2\.19\.", "CVE-2018-18074", "requests session data exposure across redirects", SeverityLevel.HIGH),
    ("lodash", r'"lodash":\s*"(?:\^|~)?4\.17\.(?:1[0-9]|20)"', "CVE-2021-23337", "Prototype pollution in lodash template", SeverityLevel.CRITICAL),
    ("pyyaml", r"pyyaml\s*==\s*5\.3\.", "CVE-2020-14343", "Arbitrary code execution through load() method", SeverityLevel.CRITICAL),
]


def _scan_dependencies_fallback(target_path: Path) -> list[Finding]:
    """Fallback scanner searching for known vulnerable dependency versions when Trivy is absent."""
    findings: list[Finding] = []
    dep_files = ["requirements.txt", "Pipfile", "pyproject.toml", "package.json", "package-lock.json"]

    for dep_filename in dep_files:
        p = target_path / dep_filename if target_path.is_dir() else (target_path if target_path.name == dep_filename else None)
        if not p or not p.exists():
            continue

        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for pkg, regex, cve, desc, severity in _KNOWN_VULNERABLE_PACKAGES:
                if re.search(regex, content, re.IGNORECASE):
                    findings.append(
                        Finding(
                            rule_id=cve,
                            description=f"{desc} in package {pkg}",
                            file_path=str(p),
                            severity=severity,
                            tool="trivy_heuristic",
                        )
                    )
        except Exception as exc:
            logger.debug("Error checking dependency file {p}: {err}", p=p, err=exc)

    return findings


async def scan_dependencies(target_path: str) -> ScanReport:
    """Scans project dependencies for known vulnerabilities and CVEs (TC-168)."""
    target = Path(target_path).resolve()
    if not target.exists():
        return ScanReport(
            tool="trivy",
            passed=False,
            error=f"Target path does not exist: {target_path}",
        )

    cmd = [
        settings.TRIVY_BIN,
        "fs",
        "--format",
        "json",
        "--scanners",
        "vuln",
        "--severity",
        "HIGH,CRITICAL",
        str(target),
    ]

    retcode, stdout, stderr = await run_scanner_process(cmd, timeout_seconds=60.0)

    if retcode == 127:
        logger.warning("Trivy binary not found in PATH, running dependency fallback scanner")
        findings = _scan_dependencies_fallback(target)
        return ScanReport(
            tool="trivy",
            passed=len(findings) == 0,
            findings=findings,
            raw_output=f"Fallback SCA heuristic ran: {len(findings)} findings",
        )

    findings: list[Finding] = []
    if stdout:
        try:
            data = json.loads(stdout)
            for res in data.get("Results", []):
                for vuln in res.get("Vulnerabilities", []):
                    raw_sev = vuln.get("Severity", "MEDIUM").upper()
                    sev = SeverityLevel.MEDIUM
                    if raw_sev == "CRITICAL":
                        sev = SeverityLevel.CRITICAL
                    elif raw_sev == "HIGH":
                        sev = SeverityLevel.HIGH
                    elif raw_sev == "LOW":
                        sev = SeverityLevel.LOW

                    findings.append(
                        Finding(
                            rule_id=vuln.get("VulnerabilityID", "CVE-UNKNOWN"),
                            description=vuln.get("Title", vuln.get("PkgName", "Dependency vulnerability")),
                            file_path=res.get("Target", ""),
                            severity=sev,
                            tool="trivy",
                        )
                    )
        except Exception as exc:
            logger.error("Failed to parse Trivy output: {err}", err=exc)

    passed = len([f for f in findings if f.severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH)]) == 0
    return ScanReport(
        tool="trivy",
        passed=passed,
        findings=findings,
        raw_output=stdout,
        error=stderr if retcode not in (0, 1) else None,
    )
