"""Semgrep SAST scanner integration."""

import json
import os
from pathlib import Path
import re
from loguru import logger

from config import settings
from scanners.base import Finding, ScanReport, SeverityLevel, run_scanner_process

_SAST_PATTERNS = [
    ("SQL_INJECTION", r"""(?:execute|raw|query)\s*\(\s*f?["'].*?(?:SELECT|INSERT|UPDATE|DELETE).*?%s|(?:\+|format\()""", SeverityLevel.HIGH),
    ("COMMAND_INJECTION", r"""(?:os\.system|subprocess\.Popen|subprocess\.call)\s*\([^)]*(?:request\.|input|sys\.argv)""", SeverityLevel.CRITICAL),
    ("EVAL_INJECTION", r"""\beval\s*\([^)]*(?:request\.|input|data)""", SeverityLevel.CRITICAL),
    ("HARDCODED_TMP_USAGE", r"""(?:open\s*\(\s*["']/tmp/)""", SeverityLevel.LOW),
]


def _scan_directory_sast_fallback(target_path: Path) -> list[Finding]:
    """Fallback SAST scanner searching for dangerous injection patterns when Semgrep binary is absent."""
    findings: list[Finding] = []
    if not target_path.exists():
        return findings

    files_to_check: list[Path] = []
    if target_path.is_file():
        files_to_check.append(target_path)
    else:
        for root, dirs, files in os.walk(target_path):
            dirs[:] = [d for d in dirs if d not in {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}]
            for f in files:
                if f.endswith((".py", ".js", ".ts", ".jsx", ".tsx", ".php")):
                    files_to_check.append(Path(root) / f)

    for file_p in files_to_check:
        try:
            content = file_p.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            for line_no, line in enumerate(lines, 1):
                for rule_id, pattern, severity in _SAST_PATTERNS:
                    if re.search(pattern, line):
                        findings.append(
                            Finding(
                                rule_id=rule_id,
                                description=f"SAST vulnerability detected matching rule {rule_id}",
                                file_path=str(file_p),
                                line_number=line_no,
                                severity=severity,
                                tool="semgrep_heuristic",
                            )
                        )
        except Exception as exc:
            logger.debug("Skipped file {p}: {err}", p=file_p, err=exc)

    return findings


async def scan_sast_semgrep(target_path: str, rules: str = "p/owasp-top-10") -> ScanReport:
    """Runs SAST security scanning against code repository (TC-167)."""
    target = Path(target_path).resolve()
    if not target.exists():
        return ScanReport(
            tool="semgrep",
            passed=False,
            error=f"Target path does not exist: {target_path}",
        )

    cmd = [
        settings.SEMGREP_BIN,
        "scan",
        "--config",
        rules,
        "--json",
        str(target),
    ]

    retcode, stdout, stderr = await run_scanner_process(cmd, timeout_seconds=60.0)

    if retcode == 127:
        logger.warning("Semgrep binary not found in PATH, running SAST fallback scanner")
        findings = _scan_directory_sast_fallback(target)
        return ScanReport(
            tool="semgrep",
            passed=len(findings) == 0,
            findings=findings,
            raw_output=f"Fallback SAST heuristic ran: {len(findings)} findings",
        )

    findings: list[Finding] = []
    if stdout:
        try:
            data = json.loads(stdout)
            results = data.get("results", [])
            for res in results:
                raw_severity = res.get("extra", {}).get("severity", "WARNING").upper()
                sev = SeverityLevel.MEDIUM
                if raw_severity == "ERROR":
                    sev = SeverityLevel.CRITICAL
                elif raw_severity == "WARNING":
                    sev = SeverityLevel.HIGH
                elif raw_severity == "INFO":
                    sev = SeverityLevel.LOW

                findings.append(
                    Finding(
                        rule_id=res.get("check_id", "sast-finding"),
                        description=res.get("extra", {}).get("message", "Security weakness detected"),
                        file_path=res.get("path", ""),
                        line_number=res.get("start", {}).get("line"),
                        severity=sev,
                        tool="semgrep",
                    )
                )
        except Exception as exc:
            logger.error("Failed to parse Semgrep JSON output: {err}", err=exc)

    passed = len([f for f in findings if f.severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH)]) == 0
    return ScanReport(
        tool="semgrep",
        passed=passed,
        findings=findings,
        raw_output=stdout,
        error=stderr if retcode not in (0, 1) else None,
    )
