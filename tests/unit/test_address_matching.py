"""Unit tests for address normalization and match keys."""

from __future__ import annotations

import pytest

from helios_geospatial.addresses import normalize_address

pytestmark = pytest.mark.unit


class TestNormalizeAddress:
    def test_strips_unit_and_canonicalizes_street_type(self) -> None:
        normalized = normalize_address("3740 S Signal Butte Road, Suite 100")
        assert normalized is not None
        assert normalized.key == "3740 S SIGNAL BUTTE RD"

    def test_matches_assessor_style_address(self) -> None:
        permit = normalize_address("3740 S SIGNAL BUTTE RD")
        parcel = normalize_address("3740 S SIGNAL BUTTE RD")
        assert permit is not None and parcel is not None
        assert permit.key == parcel.key

    def test_rejects_unparseable_strings(self) -> None:
        assert normalize_address(None) is None
        assert normalize_address("UNKNOWN") is None
        assert normalize_address("") is None
