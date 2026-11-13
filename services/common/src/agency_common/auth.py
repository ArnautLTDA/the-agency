"""Unified Inter-Service Authentication Middleware and Verification (SEC-026 / TC-177)."""

import os
from typing import Callable
from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


HEADER_AGENCY_KEY: str = "X-Agency-Key"
DEFAULT_EXEMPT_PATHS: set[str] = {
    "/health",
    "/api/v1/health",
    "/api/v1/inter/webhook",
    "/api/v1/telegram/webhook",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def get_agency_secret_key() -> str:
    """Returns the configured internal secret key, with development fallback."""
    return os.environ.get("AGENCY_SECRET_KEY", "agency_dev_secret_key_12345")


def verify_agency_key(request: Request) -> bool:
    """Verifies the X-Agency-Key header on an incoming request."""
    path = request.url.path
    if path in DEFAULT_EXEMPT_PATHS or path.rstrip("/") in DEFAULT_EXEMPT_PATHS:
        return True

    expected_key = get_agency_secret_key()
    provided_key = request.headers.get(HEADER_AGENCY_KEY)

    if not provided_key or provided_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_or_invalid_agency_key"},
        )
    return True


class AgencyKeyMiddleware(BaseHTTPMiddleware):
    """ASGI Middleware enforcing X-Agency-Key on all non-exempt endpoints."""

    def __init__(self, app: ASGIApp, exempt_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self.exempt_paths = exempt_paths or DEFAULT_EXEMPT_PATHS

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        path = request.url.path
        if path in self.exempt_paths or path.rstrip("/") in self.exempt_paths:
            return await call_next(request)

        expected_key = get_agency_secret_key()
        provided_key = request.headers.get(HEADER_AGENCY_KEY)

        if not provided_key or provided_key != expected_key:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "missing_or_invalid_agency_key"},
            )

        return await call_next(request)
