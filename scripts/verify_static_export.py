#!/usr/bin/env python3
"""Check that the published static snapshot is complete and internally honest.

Run after ``export_static_api.py``. The published site is the artefact most
people will judge Helios by, and it is assembled from flat files, so nothing at
runtime will catch a missing profile or an assertion class outside the
vocabulary. This does.

    python scripts/verify_static_export.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "apps" / "web" / "public" / "api"

FLAGSHIP = "AZ-MESA-001"

# Mirrors helios_common.vocabulary.AssertionClass. Duplicated deliberately: this
# script validates the *published bytes*, so it must not trust the code that
# produced them.
VALID_ASSERTION_CLASSES = {
    "reported",
    "extracted",
    "calculated",
    "inferred",
    "predicted",
    "unknown",
}


class VerificationError(AssertionError):
    """A published snapshot that would mislead or 404 a reader."""


def _load(path: Path) -> object:
    if not path.exists():
        raise VerificationError(f"Missing published file: {path.relative_to(REPO_ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _check_assertion_classes(records: list[dict], where: str) -> None:
    for record in records:
        value = record.get("assertion_class")
        if value not in VALID_ASSERTION_CLASSES:
            raise VerificationError(
                f"{where}: assertion class {value!r} is outside the vocabulary "
                f"{sorted(VALID_ASSERTION_CLASSES)}. The UI badges this string "
                f"directly, so an unknown value renders an inference as if it "
                f"were something else."
            )


def main() -> int:
    """Verify the export. Returns a process exit code."""
    index = _load(API_DIR / "sites.json")
    assert isinstance(index, dict)
    sites = index.get("items", [])
    if not sites:
        raise VerificationError("sites.json advertises no sites.")

    codes = {s["project_code"] for s in sites}
    if FLAGSHIP not in codes:
        raise VerificationError(f"Flagship case {FLAGSHIP} missing from {sorted(codes)}")

    # Every site the index advertises must be fetchable, or the site links into 404s.
    for code in sorted(codes):
        for relative in (f"{code}.json", f"{code}/timeline.json", f"{code}/evidence.json"):
            _load(API_DIR / "sites" / relative)

    for name in (
        "sources.json",
        "large-load-filings.json",
        "meta.json",
        "sites.geojson",
        "analytics/stages.json",
        "analytics/provenance.json",
        "map/sites.json",
        "map/infrastructure.json",
        "map/parcels.json",
    ):
        _load(API_DIR / name)

    if not (API_DIR / "sites.csv").exists():
        raise VerificationError("Missing published file: sites.csv")

    flagship = _load(API_DIR / "sites" / f"{FLAGSHIP}.json")
    assert isinstance(flagship, dict)
    if flagship.get("evidence_count", 0) <= 0:
        raise VerificationError(f"{FLAGSHIP} is published with no evidence.")

    bundle = _load(API_DIR / "sites" / FLAGSHIP / "evidence.json")
    assert isinstance(bundle, dict)
    records = bundle.get("evidence", [])
    if len(records) != flagship["evidence_count"]:
        raise VerificationError(
            f"{FLAGSHIP} advertises evidence_count={flagship['evidence_count']} "
            f"but publishes {len(records)} evidence records."
        )

    _check_assertion_classes(records, f"{FLAGSHIP} evidence")
    _check_assertion_classes(flagship.get("estimates", []), f"{FLAGSHIP} estimates")

    large_load_payload = _load(API_DIR / "large-load-filings.json")
    assert isinstance(large_load_payload, dict)
    large_load_filings = large_load_payload.get("items", [])
    if not large_load_filings:
        raise VerificationError("large-load-filings.json publishes no filing records.")
    for filing in large_load_filings:
        if filing.get("geometry") is not None:
            raise VerificationError(
                "A large-load filing publishes geometry without parcel-level evidence."
            )
        if filing.get("load_assertion_class") != "reported":
            raise VerificationError("A published contracted-load value is not marked reported.")
        digest = filing.get("source", {}).get("content_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise VerificationError(
                "A large-load filing is missing a complete source content digest."
            )
        source_url = filing.get("source", {}).get("source_url")
        if not isinstance(source_url, str) or "example.invalid" in source_url:
            raise VerificationError(
                "A large-load filing publishes a fixture placeholder instead of "
                "the official source URL."
            )

    print(
        f"OK: {len(sites)} sites published; {FLAGSHIP} carries "
        f"{len(records)} evidence records with valid assertion classes; "
        f"{len(large_load_filings)} large-load filing(s) retain source provenance."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except VerificationError as exc:
        print(f"Static export verification failed: {exc}", file=sys.stderr)
        sys.exit(1)
