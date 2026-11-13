"""Gitleaks secret scanner integration."""

import json
import os
from pathlib import Path
import re
import tempfile
from loguru import logger

from config import settings
from scanners.base import Finding, ScanReport, SeverityLevel, run_scanner_process

_SECRET_PATTERNS = [
    ("AWS_KEY", r"\b(AKIA[0-9A-Z]{16})\b", SeverityLevel.CRITICAL),
    ("PRIVATE_KEY", r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----", SeverityLevel.CRITICAL),
    ("GENERIC_API_KEY", r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]", SeverityLevel.HIGH),
    ("TELEGRAM_TOKEN", r"\b\d{8,10}:[a-zA-Z0-9_-]{35}\b", SeverityLevel.CRITICAL),
    ("GITHUB_PAT", r"\bgh[pousr]_[A-Za-z0-9_]{36,255}\b", SeverityLevel.CRITICAL),
]


def _scan_directory_regex_fallback(target_path: Path) -> list[Finding]:
    """Fallback scanner searching for high-entropy / common secrets when Gitleaks binary is absent."""
    findings: list[Finding] = []
    if not target_path.exists():
        return findings

    files_to_check: list[Path] = []
    if target_path.is_file():
        files_to_check.append(target_path)
    else:
        for root, dirs, files in os.walk(target_path):
            # Skip VCS and virtual environments
            dirs[:] = [d for d in dirs if d not in {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}]
            for f in files:
                files_to_check.append(Path(root) / f)

    for file_p in files_to_check:
        try:
            content = file_p.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            for line_no, line in enumerate(lines, 1):
                for rule_id, pattern, severity in _SECRET_PATTERNS:
                    if re.search(pattern, line):
                        findings.append(
                            Finding(
                                rule_id=rule_id,
                                description=f"Potential secret detected matching pattern {rule_id}",
                                file_path=str(file_p),
                                line_number=line_no,
                                severity=severity,
                                tool="gitleaks_heuristic",
                            )
                        )
        except Exception as exc:
            logger.debug("Skipped reading file {p}: {err}", p=file_p, err=exc)

    return findings


async def scan_secrets(target_path: str) -> ScanReport:
    """Scans repository or directory for leaked secrets and credentials (TC-166, TC-209)."""
    target = Path(target_path).resolve()
    if not target.exists():
        return ScanReport(
            tool="gitleaks",
            passed=False,
            error=f"Target path does not exist: {target_path}",
        )

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        report_file = tmp.name

    try:
        cmd = [
            settings.GITLEAKS_BIN,
            "detect",
            "--source",
            str(target),
            "--no-git",
            "--report-format",
            "json",
            "--report-path",
            report_file,
            "--exit-code",
            "2",
        ]

        retcode, stdout, stderr = await run_scanner_process(cmd, timeout_seconds=45.0)

        findings: list[Finding] = []
        if retcode == 127:
            # Gitleaks binary not found on host, execute fallback heuristic
            logger.warning("Gitleaks binary not found in PATH, using fallback secret scanner")
            findings = _scan_directory_regex_fallback(target)
            return ScanReport(
                tool="gitleaks",
                passed=len(findings) == 0,
                findings=findings,
                raw_output=f"Fallback heuristic ran: {len(findings)} findings",
            )

        if Path(report_file).exists() and os.path.getsize(report_file) > 0:
            with open(report_file, "r", encoding="utf-8") as f:
                raw_json = json.load(f)
                if isinstance(raw_json, list):
                    for item in raw_json:
                        findings.append(
                            Finding(
                                rule_id=item.get("RuleID", "secret-detected"),
                                description=item.get("Description", "Potential secret detected"),
                                file_path=item.get("File", ""),
                                line_number=item.get("StartLine"),
                                severity=SeverityLevel.CRITICAL,
                                tool="gitleaks",
                            )
                        )

        passed = len(findings) == 0 and retcode in (0, 2)
        return ScanReport(
            tool="gitleaks",
            passed=passed,
            findings=findings,
            raw_output=stdout,
            error=stderr if retcode not in (0, 2) else None,
        )
    finally:
        if os.path.exists(report_file):
            os.remove(report_file)
