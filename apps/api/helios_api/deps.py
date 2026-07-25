"""Shared FastAPI dependencies."""

from __future__ import annotations

import secrets
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from helios_common.config import Settings, get_settings
from helios_domain.session import get_session

_bearer = HTTPBearer(auto_error=False)


def db_session() -> Generator[Session, None, None]:
    """Yield a request-scoped database session."""
    yield from get_session()


DbSession = Annotated[Session, Depends(db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


class Pagination:
    """Validated pagination parameters."""

    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        """Capture pagination bounds.

        Args:
            limit: Maximum rows to return.
            offset: Rows to skip.
        """
        self.limit = limit
        self.offset = offset


PageParams = Annotated[Pagination, Depends(Pagination)]


def require_admin(
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> str:
    """Authorise an administrative request.

    Administrative routes trigger ingestion and mutate review state, so they are
    refused outright when no token is configured. Defaulting to open would mean a
    misconfigured deployment silently exposes write access.

    Args:
        settings: Application settings.
        credentials: Bearer credentials from the request.

    Returns:
        The authenticated principal name.

    Raises:
        HTTPException: If admin access is unconfigured or the token is wrong.
    """
    if not settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Administrative routes are disabled because HELIOS_ADMIN_API_TOKEN is "
                "not configured."
            ),
        )
    if credentials is None or not secrets.compare_digest(
        credentials.credentials, settings.admin_api_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing administrative bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "admin"


AdminPrincipal = Annotated[str, Depends(require_admin)]


def parse_bbox(
    bbox: Annotated[
        str | None,
        Query(description="Bounding box as min_lon,min_lat,max_lon,max_lat"),
    ] = None,
) -> tuple[float, float, float, float] | None:
    """Parse and validate a bounding-box query parameter.

    Args:
        bbox: Comma-separated bounding box.

    Returns:
        The parsed box, or ``None`` when not supplied.

    Raises:
        HTTPException: If the value is malformed or geographically invalid.
    """
    if not bbox:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bbox must contain exactly four comma-separated numbers",
        )
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bbox values must be numeric",
        ) from exc

    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="longitude values must lie between -180 and 180",
        )
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="latitude values must lie between -90 and 90",
        )
    if min_lon >= max_lon or min_lat >= max_lat:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bbox minimum values must be less than maximum values",
        )
    return (min_lon, min_lat, max_lon, max_lat)


BoundingBox = Annotated[tuple[float, float, float, float] | None, Depends(parse_bbox)]


__all__ = [
    "AdminPrincipal",
    "AppSettings",
    "BoundingBox",
    "DbSession",
    "PageParams",
    "Pagination",
    "db_session",
    "parse_bbox",
    "require_admin",
]
