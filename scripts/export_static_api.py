#!/usr/bin/env python3
"""Export the real Helios API to static JSON for GitHub Pages.

GitHub Pages cannot run FastAPI, so the published site reads flat files. The
important property is that those files are *produced by the real API* reading a
real database - not hand-written. Every assertion class, score contribution and
evidence pointer in the published output was derived by the same code that
serves a live deployment; only the transport is different.

Run it against a fixture-seeded database for a reproducible public snapshot::

    helios bootstrap          # fixtures by default, no network
    python scripts/export_static_api.py

Files are keyed by ``project_code`` rather than by the database UUID, so a
published URL such as ``/sites/AZ-MESA-001`` stays valid across rebuilds. The
JSON payloads themselves are written exactly as the API returned them - the
``id`` field inside each payload is still the true database identifier.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from helios_api.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "apps" / "web" / "public" / "api"

# Enough to cover the East Valley study area many times over; the API caps at 500.
SITE_PAGE_LIMIT = 500


class ExportError(RuntimeError):
    """Raised when the database cannot produce a publishable snapshot."""


def _write_json(client_path: str, out_path: Path, payload: Any) -> None:
    """Write ``payload`` as pretty JSON, creating parent directories."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"  {client_path:<48} -> {out_path.relative_to(OUT_DIR)}")


def _get_json(client: TestClient, path: str) -> Any:
    """GET ``path`` and return parsed JSON, raising on a non-2xx response."""
    response = client.get(path)
    response.raise_for_status()
    return response.json()


def _export_endpoint(client: TestClient, path: str, out_relative: str) -> Any:
    """Fetch one endpoint and persist it under ``OUT_DIR``."""
    payload = _get_json(client, path)
    _write_json(path, OUT_DIR / out_relative, payload)
    return payload


def _export_text(client: TestClient, path: str, out_relative: str) -> None:
    """Fetch a non-JSON endpoint (CSV) and persist it verbatim."""
    response = client.get(path)
    response.raise_for_status()
    out_path = OUT_DIR / out_relative
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(response.text, encoding="utf-8")
    print(f"  {path:<48} -> {out_path.relative_to(OUT_DIR)}")


def main() -> int:
    """Export every published endpoint. Returns a process exit code."""
    client = TestClient(app)

    print(f"Exporting static API to {OUT_DIR.relative_to(REPO_ROOT)}")

    sites = _get_json(client, f"/sites?limit={SITE_PAGE_LIMIT}")
    items = sites.get("items", [])
    if not items:
        raise ExportError(
            "The database contains no sites, so there is nothing to publish. "
            "Seed it first with `helios bootstrap` (fixtures, no network), then re-run."
        )

    # Wipe first so a renamed or removed site cannot linger as a stale file that
    # the site would happily keep serving.
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    _write_json(f"/sites?limit={SITE_PAGE_LIMIT}", OUT_DIR / "sites.json", sites)

    print(f"Exporting {len(items)} site profiles...")
    exported_codes: list[str] = []
    for site in items:
        site_id = site["id"]
        code = site["project_code"]
        exported_codes.append(code)

        _export_endpoint(client, f"/sites/{site_id}", f"sites/{code}.json")
        _export_endpoint(client, f"/sites/{site_id}/timeline", f"sites/{code}/timeline.json")
        # The evidence payload is what makes a published claim checkable.
        _export_endpoint(
            client,
            f"/exports/site/{site_id}/evidence.json",
            f"sites/{code}/evidence.json",
        )

    print("Exporting reference data...")
    _export_endpoint(client, "/sources", "sources.json")
    _export_endpoint(client, "/analytics/stages", "analytics/stages.json")
    _export_endpoint(client, "/analytics/provenance", "analytics/provenance.json")

    print("Exporting map layers...")
    _export_endpoint(client, "/map/sites", "map/sites.json")
    _export_endpoint(client, "/map/infrastructure", "map/infrastructure.json")
    _export_endpoint(client, "/map/parcels", "map/parcels.json")

    print("Exporting bulk downloads...")
    _export_text(client, "/exports/sites.csv", "sites.csv")
    _export_endpoint(client, "/exports/sites.geojson", "sites.geojson")

    # Read by the web UI's provenance banner. The published site must state what
    # it is: a snapshot, derived from recorded fixtures, exported at a point in
    # time - never implied to be a live view of county records.
    _write_json(
        "(generated)",
        OUT_DIR / "meta.json",
        {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "site_count": len(items),
            "project_codes": sorted(exported_codes),
            "note": (
                "Static snapshot exported from the Helios API. Every value was produced "
                "by the same pipeline that serves a live deployment; it is a point-in-time "
                "export, not a live view of public records."
            ),
        },
    )

    # GitHub Pages runs Jekyll by default, which strips files and directories
    # beginning with an underscore.
    (OUT_DIR / ".nojekyll").touch()

    print(f"\nDone. {len(items)} sites exported: {', '.join(sorted(exported_codes))}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ExportError as exc:
        print(f"\nExport failed: {exc}", file=sys.stderr)
        sys.exit(1)
