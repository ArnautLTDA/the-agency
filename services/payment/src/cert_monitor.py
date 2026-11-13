"""mTLS Certificate Monitor (TC-179, TC-180)."""

from datetime import datetime, timezone
from pathlib import Path
import ssl
from loguru import logger
from pydantic import BaseModel

from config import settings


class CertStatus(BaseModel):
    """mTLS Certificate status and expiration information."""

    exists: bool
    cert_path: str
    expires_at: str | None = None
    days_remaining: int | None = None
    needs_renewal: bool = False
    warning: str | None = None


def resolve_cert_path(cert_path: str) -> Path:
    """Finds certificate path relative to current working directory or repository root."""
    p = Path(cert_path)
    if p.exists():
        return p
    for parent in [Path("../../"), Path("../")]:
        candidate = (parent / cert_path).resolve()
        if candidate.exists():
            return candidate
    return p


def check_certificate_validity(cert_path: str = settings.INTER_CERT_PATH) -> CertStatus:
    """Inspects notAfter date of mTLS certificate and warns if expires in < 30 days."""
    p = resolve_cert_path(cert_path)
    if not p.exists():
        return CertStatus(
            exists=False,
            cert_path=str(p),
            warning="Certificate file not found on disk",
            needs_renewal=True,
        )

    try:
        cert_dict = ssl._ssl._test_decode_cert(str(p))
        not_after_str = cert_dict.get("notAfter")
        if not not_after_str:
            return CertStatus(exists=True, cert_path=str(p), warning="Could not decode notAfter date")

        # Format: 'May 14 12:00:00 2027 GMT'
        expires_at = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days_remaining = (expires_at - now).days
        needs_renewal = days_remaining < 30

        warning_msg = None
        if needs_renewal:
            warning_msg = f"mTLS certificate expires in {days_remaining} days (threshold is 30 days)"
            logger.warning("mTLS certificate warning: {msg}", msg=warning_msg)

        return CertStatus(
            exists=True,
            cert_path=str(p),
            expires_at=expires_at.isoformat(),
            days_remaining=days_remaining,
            needs_renewal=needs_renewal,
            warning=warning_msg,
        )
    except Exception as exc:
        logger.error("Failed to parse certificate {p}: {err}", p=p, err=exc)
        return CertStatus(exists=True, cert_path=str(p), warning=str(exc), needs_renewal=True)
