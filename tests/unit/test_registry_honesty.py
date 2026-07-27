"""Registry entries must not claim runnable status without importable code."""

from __future__ import annotations

import importlib

import pytest

from helios_common.vocabulary import ConnectorStatus
from helios_connectors.registry import SOURCE_REGISTRY, implemented_entries

pytestmark = pytest.mark.unit


class TestRegistryHonesty:
    def test_runnable_entry_points_are_importable(self) -> None:
        """IMPLEMENTED / FIXTURE_ONLY rows must resolve to a real connector class."""
        runnable = {
            ConnectorStatus.IMPLEMENTED,
            ConnectorStatus.FIXTURE_ONLY,
        }
        for entry in SOURCE_REGISTRY:
            if entry.connector_status not in runnable:
                continue
            assert entry.connector_entry_point, entry.slug
            module_name, class_name = entry.connector_entry_point.split(":")
            module = importlib.import_module(module_name)
            connector_cls = getattr(module, class_name)
            assert callable(connector_cls)

    def test_implemented_entries_helper_matches_status(self) -> None:
        slugs = {entry.slug for entry in implemented_entries()}
        assert "maricopa-assessor-parcels" in slugs
        assert "osm-power-infrastructure" in slugs
        assert "epa-echo-air-facilities" in slugs
        assert "azcc-edocket" in slugs
        # Copernicus is declared but deliberately unimplemented: it is PLANNED, so
        # it must not appear here. A fixture-backed satellite stub would have
        # advertised a capability Helios does not have.
        assert "copernicus-sentinel2" not in slugs

    def test_planned_entries_do_not_advertise_entry_points(self) -> None:
        for entry in SOURCE_REGISTRY:
            if entry.connector_status == ConnectorStatus.PLANNED:
                assert entry.connector_entry_point is None, entry.slug
