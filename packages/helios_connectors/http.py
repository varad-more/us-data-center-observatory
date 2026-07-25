"""Polite HTTP client used by every connector.

Helios reads public records from small municipal servers. Being a good citizen
is both an ethical obligation and a practical one - a connector that hammers a
county portal will be blocked, and the project loses the source permanently.

This client therefore enforces, by default and without connector opt-in:

* a per-host token-bucket rate limit,
* exponential backoff with jitter on transient failures,
* ``Retry-After`` compliance on 429 and 503,
* conditional requests via ``ETag`` / ``If-Modified-Since``,
* an honest, contactable ``User-Agent``.

It deliberately provides no mechanism for bypassing authentication, CAPTCHAs, or
access controls.
"""

from __future__ import annotations

import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from helios_common.config import Settings, get_settings
from helios_common.logging import get_logger

logger = get_logger(__name__)

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
"""Statuses worth retrying. 4xx codes outside this set indicate a client bug."""


class FetchBlockedError(RuntimeError):
    """Raised when live fetching is disabled by configuration.

    Tests set ``allow_live_fetch=False`` so that a connector accidentally
    reaching the network fails loudly instead of producing flaky results.
    """


class RateLimiter:
    """Per-host token bucket.

    A single shared instance across a connector run means concurrent requests to
    the same host cooperate, while requests to different hosts do not block each
    other unnecessarily.
    """

    def __init__(self, default_rate_per_second: float = 2.0) -> None:
        """Initialise the limiter.

        Args:
            default_rate_per_second: Requests per second allowed per host when a
                source does not declare its own limit.
        """
        self.default_rate = max(default_rate_per_second, 0.01)
        self._host_rates: dict[str, float] = {}
        self._next_available: dict[str, float] = defaultdict(float)

    def configure_host(self, host: str, rate_per_second: float) -> None:
        """Set an explicit rate for one host."""
        self._host_rates[host] = max(rate_per_second, 0.01)

    def acquire(self, url: str) -> float:
        """Block until a request to ``url`` is permitted.

        Args:
            url: The URL about to be requested.

        Returns:
            Seconds spent waiting, for telemetry.
        """
        host = urlparse(url).netloc or "unknown"
        rate = self._host_rates.get(host, self.default_rate)
        interval = 1.0 / rate

        now = time.monotonic()
        earliest = self._next_available[host]
        wait = max(0.0, earliest - now)
        if wait > 0:
            time.sleep(wait)
        self._next_available[host] = max(now, earliest) + interval
        return wait


@dataclass(slots=True)
class HttpStats:
    """Per-run HTTP telemetry, folded into the connector-run record."""

    status_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    retries: int = 0
    bytes_downloaded: int = 0
    requests: int = 0
    rate_limit_wait_seconds: float = 0.0
    not_modified: int = 0

    def record(self, status: int | None, size: int) -> None:
        """Record one completed response."""
        self.requests += 1
        self.bytes_downloaded += size
        key = str(status) if status is not None else "error"
        self.status_counts[key] += 1
        if status == 304:
            self.not_modified += 1

    def as_dict(self) -> dict[str, Any]:
        """Serialise for storage on ``connector_runs``."""
        return {
            "status_counts": dict(self.status_counts),
            "retries": self.retries,
            "bytes_downloaded": self.bytes_downloaded,
            "requests": self.requests,
            "rate_limit_wait_seconds": round(self.rate_limit_wait_seconds, 3),
            "not_modified": self.not_modified,
        }


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """A normalised HTTP response."""

    url: str
    status_code: int
    content: bytes
    headers: dict[str, str]
    elapsed_ms: float
    from_cache: bool = False

    @property
    def mime_type(self) -> str:
        """Content type with parameters stripped, defaulting to octet-stream."""
        raw = self.headers.get("content-type", "application/octet-stream")
        return raw.split(";", 1)[0].strip().lower()

    @property
    def etag(self) -> str | None:
        """Entity tag, if the server supplied one."""
        return self.headers.get("etag")

    @property
    def last_modified(self) -> str | None:
        """Last-Modified header, if present."""
        return self.headers.get("last-modified")


class PoliteHttpClient:
    """Rate-limited, retrying HTTP client with conditional-request support."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        rate_limiter: RateLimiter | None = None,
        transport: httpx.BaseTransport | None = None,
        stats: HttpStats | None = None,
    ) -> None:
        """Initialise the client.

        Args:
            settings: Configuration; defaults to process settings.
            rate_limiter: Shared limiter; a fresh one is created if omitted.
            transport: Custom transport, used by tests to stub the network.
            stats: Shared stats object to accumulate into.
        """
        self.settings = settings or get_settings()
        self.rate_limiter = rate_limiter or RateLimiter(self.settings.default_rate_limit_per_second)
        self.stats = stats or HttpStats()
        self._client = httpx.Client(
            timeout=httpx.Timeout(self.settings.http_timeout_seconds),
            follow_redirects=True,
            transport=transport,
            headers={
                "User-Agent": self.settings.user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
        )

    def __enter__(self) -> PoliteHttpClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._client.close()

    def _backoff_seconds(self, attempt: int, retry_after: str | None) -> float:
        """Compute the delay before the next attempt.

        Honours ``Retry-After`` when the server supplies it, otherwise uses
        exponential backoff with full jitter to avoid synchronised retries.
        """
        if retry_after:
            try:
                return min(float(retry_after), self.settings.http_backoff_max_seconds)
            except ValueError:
                pass  # Retry-After may be an HTTP-date; fall through to backoff.
        base = self.settings.http_backoff_base_seconds * (2**attempt)
        return min(base, self.settings.http_backoff_max_seconds) * (0.5 + random.random() / 2)

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> HttpResponse:
        """Perform a request with rate limiting, retries, and conditional headers.

        Args:
            method: HTTP method.
            url: Absolute URL.
            params: Query parameters.
            data: Form body for POST requests.
            headers: Extra request headers.
            etag: Prior ``ETag``; sent as ``If-None-Match``.
            last_modified: Prior ``Last-Modified``; sent as ``If-Modified-Since``.

        Returns:
            The response. A 304 is returned as-is with ``from_cache`` set.

        Raises:
            FetchBlockedError: If live fetching is disabled.
            httpx.HTTPError: If every attempt fails.
        """
        if not self.settings.allow_live_fetch:
            raise FetchBlockedError(
                f"Live fetching is disabled (HELIOS_ALLOW_LIVE_FETCH=false); refused {url!r}"
            )

        request_headers = dict(headers or {})
        if etag:
            request_headers["If-None-Match"] = etag
        if last_modified:
            request_headers["If-Modified-Since"] = last_modified

        last_error: Exception | None = None
        for attempt in range(self.settings.http_max_retries + 1):
            self.stats.rate_limit_wait_seconds += self.rate_limiter.acquire(url)
            started = time.monotonic()
            try:
                response = self._client.request(
                    method, url, params=params, data=data, headers=request_headers
                )
            except httpx.HTTPError as exc:
                last_error = exc
                self.stats.record(None, 0)
                if attempt >= self.settings.http_max_retries:
                    break
                self.stats.retries += 1
                delay = self._backoff_seconds(attempt, None)
                logger.warning(
                    "http.transport_error", url=url, attempt=attempt, delay=delay, error=str(exc)
                )
                time.sleep(delay)
                continue

            elapsed_ms = (time.monotonic() - started) * 1000
            self.stats.record(response.status_code, len(response.content))

            if response.status_code in RETRYABLE_STATUS:
                if attempt >= self.settings.http_max_retries:
                    response.raise_for_status()
                self.stats.retries += 1
                delay = self._backoff_seconds(attempt, response.headers.get("retry-after"))
                logger.warning(
                    "http.retryable_status",
                    url=url,
                    status=response.status_code,
                    attempt=attempt,
                    delay=delay,
                )
                time.sleep(delay)
                continue

            if response.status_code >= 400 and response.status_code != 304:
                response.raise_for_status()

            return HttpResponse(
                url=str(response.url),
                status_code=response.status_code,
                content=response.content,
                headers={k.lower(): v for k, v in response.headers.items()},
                elapsed_ms=elapsed_ms,
                from_cache=response.status_code == 304,
            )

        message = f"Exhausted {self.settings.http_max_retries + 1} attempts for {url!r}"
        raise httpx.HTTPError(message) from last_error

    def get(self, url: str, **kwargs: Any) -> HttpResponse:
        """Perform a GET request."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> HttpResponse:
        """Perform a POST request."""
        return self.request("POST", url, **kwargs)


__all__ = [
    "RETRYABLE_STATUS",
    "FetchBlockedError",
    "HttpResponse",
    "HttpStats",
    "PoliteHttpClient",
    "RateLimiter",
]
