"""The region registry must stay internally consistent and honest about coverage.

A malformed region does not fail loudly at the point of use. It mints a project
code with a blank state prefix, or bounds a query with a box that matches
nothing, and the result looks like an absence of sites rather than a bug.
"""

from __future__ import annotations

import pytest

from helios_common.config import get_settings
from helios_domain.regions import (
    DEFAULT_REGION_SLUG,
    EAST_VALLEY_AZ,
    REGIONS,
    RegionCoverage,
    UnknownRegionError,
    active_regions,
    get_region,
    region_slugs,
    resolve_region,
)

pytestmark = pytest.mark.unit


class TestRegistryShape:
    def test_slugs_are_unique(self) -> None:
        slugs = region_slugs()
        assert len(set(slugs)) == len(slugs)

    def test_every_region_is_well_formed(self) -> None:
        """The import-time validator should already have caught these; asserting
        them here means a regression names the field rather than the module."""
        for region in REGIONS:
            assert len(region.state_code) == 2 and region.state_code.isupper(), region.slug
            assert region.counties, region.slug
            assert region.note.strip(), region.slug
            min_lon, min_lat, max_lon, max_lat = region.bbox
            assert min_lon < max_lon and min_lat < max_lat, region.slug

    def test_default_region_is_registered_and_active(self) -> None:
        default = get_region(DEFAULT_REGION_SLUG)
        assert default is EAST_VALLEY_AZ
        assert default.is_active

    def test_settings_study_region_is_registered(self) -> None:
        """Settings names a region by slug. If that slug is not in the registry,
        every bounded connector query silently loses its bounding box."""
        assert get_region(get_settings().study_region_slug) is not None


class TestCoverageHonesty:
    def test_only_regions_with_connectors_are_active(self) -> None:
        """Helios reads exactly one region today. Marking another ACTIVE would
        claim a coverage that does not exist."""
        assert [region.slug for region in active_regions()] == ["east-valley-az"]

    def test_declared_regions_are_named_not_claimed(self) -> None:
        declared = [r for r in REGIONS if r.coverage is RegionCoverage.DECLARED]
        assert declared, "the registry should record where Helios intends to go"
        for region in declared:
            assert not region.is_active, region.slug


class TestLookup:
    def test_resolve_accepts_a_region_or_a_slug(self) -> None:
        assert resolve_region(EAST_VALLEY_AZ) is EAST_VALLEY_AZ
        assert resolve_region("east-valley-az") is EAST_VALLEY_AZ

    def test_unknown_slug_raises_and_lists_what_is_registered(self) -> None:
        with pytest.raises(UnknownRegionError) as excinfo:
            get_region("east-valley-arizona")
        assert "east-valley-az" in str(excinfo.value)


class TestProjectCodePrefix:
    def test_prefix_carries_the_region_state(self) -> None:
        assert EAST_VALLEY_AZ.project_code_prefix("MESA") == "AZ-MESA"
        assert get_region("northern-virginia").project_code_prefix("ASHBURN") == "VA-ASHBURN"

    def test_no_two_regions_in_one_state_would_collide_on_a_shared_city(self) -> None:
        """Project codes are unique per (state, city), not per region. Two AZ
        regions sharing a city name would compete for the same sequence, which is
        harmless only because the sequence is looked up by prefix."""
        by_state: dict[str, set[str]] = {}
        for region in REGIONS:
            overlap = by_state.setdefault(region.state_code, set()) & set(region.cities_upper)
            assert not overlap, f"{region.slug} repeats {overlap} within {region.state_code}"
            by_state[region.state_code].update(region.cities_upper)
