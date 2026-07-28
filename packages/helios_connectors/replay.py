"""Replay of recorded source payloads through the real ingestion pipeline.

Helios ships fixtures captured from live public sources so that the observatory
can be rebuilt without touching a county server. Replay is deliberately *not* a
mock layer: a replayed connector runs the same ``parse``, ``normalize``,
``validate`` and load code a live run does, and the pipeline still hashes bytes,
versions documents, and mints evidence. Only the network call is substituted.

That distinction is what makes the published static export honest. Every
assertion class on the deployed site was derived by the same rules that would
run against the live source; the bytes those rules read were simply recorded
earlier rather than fetched now.

Two flavours exist, and they are not interchangeable:

* :class:`~helios_connectors.base.FixtureBackedConnector` is for sources whose
  live interface cannot be accessed responsibly at all (ACC eDocket). Those
  connectors read fixtures in production and declare ``FIXTURE_ONLY`` status.
* :func:`replay_connector` is for sources that *do* have a working live
  connector, letting an operator or CI rebuild offline without pretending the
  source is inaccessible. Registry status is untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from helios_connectors.area_totals import (
    EiaStateElectricityConnector,
    UsgsCountyWaterConnector,
)
from helios_connectors.azcc_edocket import AzccEdocketConnector, default_fixture_dir
from helios_connectors.epa_echo import EpaEchoAirConnector
from helios_connectors.maricopa_assessor import MaricopaAssessorConnector
from helios_connectors.mesa_permits import MesaBuildingPermitsConnector
from helios_connectors.osm_power import OsmPowerConnector
from helios_connectors.types import (
    DateRange,
    DiscoveryResult,
    FetchResult,
    RawDocument,
    SourceItem,
)

if TYPE_CHECKING:
    from helios_connectors.base import BaseConnector

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
"""Repository fixture root. Fixtures are product data, not test-only data."""

# A fixed timestamp keeps replay runs byte-identical, which is what lets CI
# assert that a regenerated static export matches the committed one.
REPLAY_RETRIEVED_AT = datetime(2026, 7, 25, 21, 30, tzinfo=UTC)


class FixtureNotFoundError(FileNotFoundError):
    """Raised when a declared replay fixture is missing from disk."""


def load_fixture_bytes(*parts: str) -> bytes:
    """Read a recorded payload exactly as it was captured from the source.

    Args:
        *parts: Path components below the repository ``fixtures`` root.

    Returns:
        The raw bytes of the fixture.

    Raises:
        FixtureNotFoundError: If no fixture exists at that path.
    """
    path = FIXTURES_ROOT.joinpath(*parts)
    if not path.exists():
        raise FixtureNotFoundError(f"Missing fixture: {path}")
    return path.read_bytes()


_FIXTURE_MIME_TYPES: dict[str, str] = {
    ".json": "application/json",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _mime_for(fixture_parts: tuple[str, ...]) -> str:
    """Return the content type a live fetch of this fixture would have carried.

    Replay is meant to be indistinguishable from a live run downstream of the
    network, so a recorded spreadsheet must not arrive claiming to be JSON.
    """
    suffix = Path(fixture_parts[-1]).suffix.lower() if fixture_parts else ""
    return _FIXTURE_MIME_TYPES.get(suffix, "application/octet-stream")


def replay_connector(
    connector_cls: type[BaseConnector],
    fixture_parts: tuple[str, ...],
    native_id: str,
    *,
    payload: bytes | None = None,
    **kwargs: Any,
) -> BaseConnector:
    """Build a connector that replays a recorded payload instead of fetching.

    Discovery and fetch are overridden; everything downstream of them - parsing,
    normalization, hashing, versioning, loading - runs unchanged, so a replay
    exercises the pipeline end to end with the live source removed.

    Args:
        connector_cls: The real connector class to subclass.
        fixture_parts: Path components below the fixtures root.
        native_id: Stable source-native identifier for the recorded item. Held
            constant across runs so re-ingesting an unchanged fixture is a no-op.
        payload: Raw bytes to replay instead of reading ``fixture_parts``.
        **kwargs: Forwarded to the connector constructor.

    Returns:
        An instance of an anonymous subclass of ``connector_cls``.
    """
    content = payload if payload is not None else load_fixture_bytes(*fixture_parts)
    mime_type = _mime_for(fixture_parts)

    class _Replay(connector_cls):  # type: ignore[valid-type, misc]
        def discover(self, date_range: DateRange) -> DiscoveryResult:
            return DiscoveryResult(
                items=[
                    SourceItem(
                        source_native_id=native_id,
                        url="https://example.invalid/recorded",
                        title="Recorded fixture",
                        document_type="fixture",
                    )
                ]
            )

        def fetch(self, item: SourceItem) -> FetchResult:
            return FetchResult(
                document=RawDocument(
                    item=item,
                    payload=content,
                    mime_type=mime_type,
                    retrieved_at=REPLAY_RETRIEVED_AT,
                    http_status=200,
                    headers={"content-type": mime_type, "etag": '"abc123"'},
                    etag='"abc123"',
                )
            )

    return _Replay(**kwargs)


# Connector slug -> how to rebuild it from recorded bytes. Ordering matters at
# the call site, not here: Mesa permits match against assessor parcels, so the
# assessor must be ingested first (see ``FIXTURE_INGEST_ORDER``).
FIXTURE_REPLAYS: dict[str, tuple[type[BaseConnector], tuple[str, ...], str]] = {
    "maricopa-assessor-parcels": (
        MaricopaAssessorConnector,
        ("maricopa_assessor", "east_valley_data_centers.json"),
        "parcel-query:fixture:offset:0",
    ),
    "osm-power-infrastructure": (
        OsmPowerConnector,
        ("osm_power", "east_valley_power.json"),
        "overpass:power:east-valley",
    ),
    "epa-echo-air-facilities": (
        EpaEchoAirConnector,
        ("epa_echo", "mesa_air_facilities.json"),
        "echo:air:east-valley",
    ),
    "mesa-building-permits": (
        MesaBuildingPermitsConnector,
        ("mesa_permits", "east_valley_com.json"),
        "mesa:permits:east-valley",
    ),
    "usgs-county-water-use": (
        UsgsCountyWaterConnector,
        ("usgs_water", "arizona_counties_2015.csv"),
        "usgs:water:arizona-counties:2015",
    ),
    "eia-state-electricity-sales": (
        EiaStateElectricityConnector,
        ("eia_electricity", "sales_annual.xlsx"),
        "eia:sales:states:latest",
    ),
}

FIXTURE_INGEST_ORDER: tuple[str, ...] = (
    "maricopa-assessor-parcels",
    "osm-power-infrastructure",
    "epa-echo-air-facilities",
    # Address matching needs assessor parcels already loaded.
    "mesa-building-permits",
    # Area totals stand alone; they describe a county or state, not a site, so
    # they neither depend on nor are depended on by anything above.
    "usgs-county-water-use",
    "eia-state-electricity-sales",
    # Fixture-only in production; no replay wrapper needed.
    "azcc-edocket",
)


def build_fixture_connector(slug: str, **kwargs: Any) -> BaseConnector:
    """Return an offline connector for ``slug``.

    ``azcc-edocket`` is already fixture-backed in production and is returned
    as-is; everything else is wrapped in a replay.

    Args:
        slug: A connector slug present in :data:`FIXTURE_INGEST_ORDER`.
        **kwargs: Forwarded to the connector constructor.

    Returns:
        A connector that performs no network access.

    Raises:
        KeyError: If ``slug`` has no recorded fixture.
    """
    if slug == "azcc-edocket":
        return AzccEdocketConnector(fixture_root=default_fixture_dir(), **kwargs)

    if slug not in FIXTURE_REPLAYS:
        raise KeyError(
            f"No fixture replay declared for {slug!r}. "
            f"Available: {', '.join(sorted(FIXTURE_REPLAYS))}, azcc-edocket"
        )

    connector_cls, fixture_parts, native_id = FIXTURE_REPLAYS[slug]
    return replay_connector(connector_cls, fixture_parts, native_id, **kwargs)


__all__ = [
    "FIXTURES_ROOT",
    "FIXTURE_INGEST_ORDER",
    "FIXTURE_REPLAYS",
    "FixtureNotFoundError",
    "build_fixture_connector",
    "load_fixture_bytes",
    "replay_connector",
]
