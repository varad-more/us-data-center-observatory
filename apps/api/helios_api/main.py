"""The Helios FastAPI application."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from helios_api.routers import (
    admin,
    analytics,
    exports,
    map_layers,
    regions,
    sites,
    sources,
)
from helios_api.schemas import HealthResponse, ReadinessResponse
from helios_common.config import get_settings
from helios_common.logging import configure_logging, get_logger
from helios_domain.session import get_engine

logger = get_logger(__name__)

DESCRIPTION = """
**Helios US AI Infrastructure Observatory** - transparent early-warning
intelligence for AI infrastructure development.

Helios assembles public records into an evidence-backed, temporal view of how
data-centre projects progress from land acquisition through permitting,
construction, grid connection, and operation.

### Reading Helios output

Every value carries an **assertion class** describing how it was established:

| Class | Meaning |
|---|---|
| `reported` | Stated directly by an authoritative source |
| `extracted` | Read from a document by a parser, with a citable span |
| `calculated` | Derived deterministically from stored values |
| `inferred` | Concluded from indirect signals; may be wrong |
| `predicted` | Model output about an unobserved state |
| `unknown` | Explicitly not established |

Confidence scores are **model output, not fact**. Helios does not assert who
operates or will operate a facility unless a direct filing establishes it;
shell-company indicators are flags for human review, never attributions.

### Provenance

Every evidence record cites an immutable, content-addressed document version and
a locator within it. `GET /exports/site/{site_id}/bundle.zip` returns everything
needed to verify a conclusion independently.
"""


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Configure logging on startup and dispose of connections on shutdown."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    logger.info("api.starting", environment=settings.environment, version=settings.api_version)
    yield
    get_engine().dispose()
    logger.info("api.stopped")


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=DESCRIPTION,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "sites", "description": "Suspected and confirmed development sites."},
            {"name": "map", "description": "GeoJSON layers for the interactive map."},
            {
                "name": "sources",
                "description": (
                    "The source registry, including sources Helios cannot currently "
                    "access and why."
                ),
            },
            {"name": "analytics", "description": "Regional analytics and data-quality metrics."},
            {"name": "exports", "description": "CSV, GeoJSON, and verifiable evidence bundles."},
            {"name": "admin", "description": "Protected operational endpoints."},
        ],
        contact={
            "name": "Project Helios",
            "url": "https://github.com/varad-more/us-data-center-observatory",
        },
        license_info={"name": "Apache-2.0", "url": "https://www.apache.org/licenses/LICENSE-2.0"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Emit a structured log line and a latency header for every request."""
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"
        logger.info(
            "api.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(elapsed_ms, 1),
        )
        return response

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Liveness probe. Does not touch the database."""
        return HealthResponse(
            status="ok", version=settings.api_version, environment=settings.environment
        )

    @app.get("/ready", response_model=ReadinessResponse, tags=["health"])
    def ready() -> JSONResponse:
        """Readiness probe, verifying database and PostGIS availability."""
        checks: dict[str, str] = {}
        ok = True
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
                checks["database"] = "ok"
                version = connection.execute(text("SELECT postgis_version()")).scalar()
                checks["postgis"] = str(version)
        except Exception as exc:
            ok = False
            checks["database"] = f"error: {type(exc).__name__}"

        payload = ReadinessResponse(ready=ok, checks=checks)
        return JSONResponse(status_code=200 if ok else 503, content=payload.model_dump())

    app.include_router(sites.router)
    app.include_router(map_layers.router)
    app.include_router(sources.router)
    app.include_router(regions.router)
    app.include_router(analytics.router)
    app.include_router(exports.router)
    app.include_router(admin.router)

    return app


app = create_app()

__all__ = ["app", "create_app"]
