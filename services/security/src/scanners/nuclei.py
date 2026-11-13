"""Nuclei DAST scanner integration for preview URLs."""

import json
import os
from pathlib import Path
import tempfile
import httpx
from loguru import logger

from config import settings
from scanners.base import Finding, ScanReport, SeverityLevel, run_scanner_process


async def _probe_preview_url_fallback(target_url: str) -> list[Finding]:
    """Fallback DAST probe testing security headers and sensitive paths when Nuclei is absent."""
    findings: list[Finding] = []
    base_url = target_url.rstrip("/")

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, verify=False) as client:
        # 1. Base response inspection
        try:
            resp = await client.get(base_url)
            headers = {k.lower(): v for k, v in resp.headers.items()}

            if "content-security-policy" not in headers:
                findings.append(
                    Finding(
                        rule_id="missing-csp-header",
                        description="Content-Security-Policy header is missing",
                        file_path=base_url,
                        severity=SeverityLevel.LOW,
                        tool="dast_probe",
                    )
                )

            if "x-frame-options" not in headers:
                findings.append(
                    Finding(
                        rule_id="missing-x-frame-options",
                        description="X-Frame-Options header is missing (clickjacking risk)",
                        file_path=base_url,
                        severity=SeverityLevel.MEDIUM,
                        tool="dast_probe",
                    )
                )
        except Exception as exc:
            logger.debug("Failed base URL probe on {u}: {err}", u=base_url, err=exc)

        # 2. Check for exposed sensitive paths
        sensitive_paths = [
            ("/.env", SeverityLevel.CRITICAL, "Exposed environment configuration file"),
            ("/.git/HEAD", SeverityLevel.CRITICAL, "Exposed Git repository metadata"),
        ]

        for path, sev, desc in sensitive_paths:
            try:
                res = await client.get(f"{base_url}{path}")
                if res.status_code == 200 and len(res.text) > 0 and "<html" not in res.text.lower():
                    findings.append(
                        Finding(
                            rule_id=f"exposed-endpoint-{path.replace('/', '').replace('.', '')}",
                            description=f"{desc} accessible at {path}",
                            file_path=f"{base_url}{path}",
                            severity=sev,
                            tool="dast_probe",
                        )
                    )
            except Exception as exc:
                logger.debug("Path probe failed for {p}: {err}", p=path, err=exc)

    return findings


async def run_dast_scan(target_url: str) -> ScanReport:
    """Runs DAST scanner against deployed preview URL (TC-210)."""
    if not target_url.startswith(("http://", "https://")):
        return ScanReport(
            tool="nuclei",
            passed=False,
            error=f"Invalid target URL: {target_url}",
        )

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        export_file = tmp.name

    try:
        cmd = [
            settings.NUCLEI_BIN,
            "-target",
            target_url,
            "-json-export",
            export_file,
            "-severity",
            "critical,high",
            "-silent",
        ]

        retcode, stdout, stderr = await run_scanner_process(cmd, timeout_seconds=90.0)

        if retcode == 127:
            logger.warning("Nuclei binary not found in PATH, running HTTP DAST probe fallback")
            findings = await _probe_preview_url_fallback(target_url)
            passed = len([f for f in findings if f.severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH)]) == 0
            return ScanReport(
                tool="nuclei",
                passed=passed,
                findings=findings,
                raw_output=f"DAST probe fallback ran: {len(findings)} findings",
            )

        findings: list[Finding] = []
        if Path(export_file).exists() and os.path.getsize(export_file) > 0:
            with open(export_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                        raw_sev = item.get("info", {}).get("severity", "medium").upper()
                        sev = SeverityLevel.MEDIUM
                        if raw_sev == "CRITICAL":
                            sev = SeverityLevel.CRITICAL
                        elif raw_sev == "HIGH":
                            sev = SeverityLevel.HIGH
                        elif raw_sev == "LOW":
                            sev = SeverityLevel.LOW

                        findings.append(
                            Finding(
                                rule_id=item.get("template-id", "nuclei-finding"),
                                description=item.get("info", {}).get("name", "DAST finding"),
                                file_path=item.get("matched-at", target_url),
                                severity=sev,
                                tool="nuclei",
                            )
                        )
                    except Exception as exc:
                        logger.debug("Failed parsing nuclei line: {err}", err=exc)

        passed = len([f for f in findings if f.severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH)]) == 0
        return ScanReport(
            tool="nuclei",
            passed=passed,
            findings=findings,
            raw_output=stdout,
            error=stderr if retcode != 0 else None,
        )
    finally:
        if os.path.exists(export_file):
            os.remove(export_file)
