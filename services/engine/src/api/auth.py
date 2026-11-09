"""API Key Authentication Dependency (SEC-003)."""

import secrets
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from src.config import get_settings

API_KEY_HEADER = APIKeyHeader(name="X-Engine-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> str:
    """Validates the static API Key from the X-Engine-Key header in constant time."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )

    settings = get_settings()
    expected_key = settings.ENGINE_API_KEY

    # Use secrets.compare_digest to prevent timing attacks (TC-044)
    if not secrets.compare_digest(api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )

    return api_key
