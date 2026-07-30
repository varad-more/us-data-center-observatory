"""Registry entries must not claim runnable status without importable code."""

from __future__ import annotations

import importlib

import pytest

from helios_common.vocabulary import ConnectorStatus
from helios_connectors.registry import SOURCE_REGISTRY, get_entry, implemented_entries
from helios_worker.cli import CONNECTORS

pytestmark = pytest.mark.unit


class TestRegistryHonesty:
    def test_connector_status_vocabulary_contains_only_reachable_states(self) -> None:
        """Every public status must have a producer, not just a UI label."""
        assert set(ConnectorStatus) == {
            ConnectorStatus.PLANNED,
            ConnectorStatus.FIXTURE_ONLY,
            ConnectorStatus.IMPLEMENTED,
            ConnectorStatus.WITHDRAWN,
        }

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

    def test_mpsc_large_load_connector_is_runnable_from_cli(self) -> None:
        """The public IMPLEMENTED claim must include the operational dispatch path."""
        entry = get_entry("mpsc-large-load-contracts")

        assert entry.connector_status == ConnectorStatus.IMPLEMENTED
        assert entry.connector_slug in CONNECTORS

    def test_planned_entries_do_not_advertise_entry_points(self) -> None:
        for entry in SOURCE_REGISTRY:
            if entry.connector_status == ConnectorStatus.PLANNED:
                assert entry.connector_entry_point is None, entry.slug

    def test_ferc_large_load_proceeding_is_a_gap_not_current_coverage(self) -> None:
        entry = get_entry("ferc-large-load-interconnection")

        assert entry.connector_status == ConnectorStatus.PLANNED
        assert entry.connector_slug is None
        assert entry.connector_entry_point is None
        assert entry.base_url == "https://www.ferc.gov/rm26-4"
        assert entry.access_limitation is not None
        assert "do not yet provide" in entry.access_limitation
        assert "no current interconnection coverage" in entry.access_limitation
        assert entry.notes is not None
        assert "NYISO order specifically" in entry.notes
        assert "six" in entry.notes and "tailored" in entry.notes

    def test_tags_describe_sources_not_project_scheduling(self) -> None:
        """Status carries delivery posture; tags should describe the data itself."""
        for entry in SOURCE_REGISTRY:
            assert all("phase" not in tag for tag in entry.tags), entry.slug

    def test_withdrawn_entries_have_no_connector_and_say_why(self) -> None:
        """WITHDRAWN means the publisher took the data away, not that we were lazy.

        The status only earns its place in the vocabulary if it carries the
        reason with it; a bare "withdrawn" pill would tell a reader less than
        the PLANNED it replaced.
        """
        withdrawn = [
            entry
            for entry in SOURCE_REGISTRY
            if entry.connector_status == ConnectorStatus.WITHDRAWN
        ]
        assert withdrawn, "the status exists because HIFLD substations went away"
        for entry in withdrawn:
            assert entry.connector_entry_point is None, entry.slug
            assert entry.connector_slug is None, entry.slug
            assert entry.access_limitation, entry.slug

    def test_withdrawn_entries_are_not_runnable(self) -> None:
        slugs = {entry.slug for entry in implemented_entries()}
        assert "hifld-electric-substations" not in slugs
