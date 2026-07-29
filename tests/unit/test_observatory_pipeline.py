"""Tests for the observatory data pipeline.

Every case here corresponds to a defect that was actually hit, or to a claim the
published site makes that would be wrong if the code drifted. The pipeline turns
volunteer-mapped geometry into figures about national infrastructure, and the
ways it can go quietly wrong all look like plausible output.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "observatory"
sys.path.insert(0, str(SCRIPTS))

from _common import BoundingBox, tile, us_tiles, write_csv  # noqa: E402
from build_series import _month_range, build  # noqa: E402
from fetch_osm_history import _kind_of, _split_osm_id  # noqa: E402
from fetch_osm_snapshot import _ring_area_m2, normalise  # noqa: E402


class TestGeodesicArea:
    """Footprint is the weight the whole power allocation rests on."""

    def test_one_degree_square_is_not_treated_as_metres(self) -> None:
        """A degrees-as-metres bug would make this about 1 m2 instead of 1e10."""
        ring = [(0.0, 0.0), (0.1, 0.0), (0.1, 0.1), (0.0, 0.1), (0.0, 0.0)]
        area = _ring_area_m2(ring)
        # 0.1 degree near the equator is ~11.1 km, so ~1.23e8 m2.
        assert 1.1e8 < area < 1.3e8

    def test_area_shrinks_with_latitude(self) -> None:
        """The same degree box covers less ground near the pole.

        A planar approximation would return identical areas, which is how an
        Alaskan facility ends up weighted like an equatorial one.
        """
        equator = _ring_area_m2([(0.0, 0.0), (0.1, 0.0), (0.1, 0.1), (0.0, 0.1), (0.0, 0.0)])
        far_north = _ring_area_m2([(0.0, 60.0), (0.1, 60.0), (0.1, 60.1), (0.0, 60.1), (0.0, 60.0)])
        assert far_north < equator * 0.55

    def test_degenerate_ring_has_no_area(self) -> None:
        assert _ring_area_m2([(0.0, 0.0), (1.0, 1.0)]) == 0.0


class TestNormalise:
    """Rows the fetch produces feed straight into county assignment."""

    def test_way_gets_centroid_and_footprint(self) -> None:
        element = {
            "type": "way",
            "id": 42,
            "tags": {"telecom": "data_center", "name": "Example DC"},
            "geometry": [
                {"lat": 39.0, "lon": -77.5},
                {"lat": 39.0, "lon": -77.4},
                {"lat": 39.1, "lon": -77.4},
                {"lat": 39.1, "lon": -77.5},
            ],
        }
        row = normalise(element)
        assert row is not None
        assert row["osm_type"] == "way"
        assert float(row["footprint_m2"]) > 0
        assert -77.5 < float(row["lon"]) < -77.4
        assert 39.0 < float(row["lat"]) < 39.1

    def test_node_without_geometry_still_places(self) -> None:
        row = normalise(
            {"type": "node", "id": 7, "lat": 33.4, "lon": -111.9, "tags": {"name": "N"}}
        )
        assert row is not None
        assert float(row["footprint_m2"]) == 0.0
        assert float(row["lat"]) == pytest.approx(33.4)

    def test_element_with_no_position_is_dropped(self) -> None:
        """Returning a row with no coordinate would place it in no county and
        silently vanish from every regional total."""
        assert normalise({"type": "relation", "id": 1, "tags": {}}) is None

    def test_no_build_date_is_ever_emitted(self) -> None:
        """OpenStreetMap carries no construction dates, so nothing may claim one."""
        row = normalise(
            {
                "type": "node",
                "id": 9,
                "lat": 1.0,
                "lon": 1.0,
                "tags": {"start_date": "2019", "name": "X"},
            }
        )
        assert row is not None
        assert "start_date" not in row
        assert "built_on" not in row
        # first_seen exists but is filled from mapping history, never from tags.
        assert row["first_seen"] == ""


class TestContributionKinds:
    """ohsome flags decide whether a count moves."""

    def test_creation_outranks_edits(self) -> None:
        assert _kind_of({"@creation": True, "@tagChange": True}) == "creation"

    def test_deletion_outranks_edits(self) -> None:
        assert _kind_of({"@deletion": True, "@geometryChange": True}) == "deletion"

    def test_missing_flags_yield_no_kind(self) -> None:
        """Requesting ohsome without `contributionTypes` returns exactly this:
        contributions with an id and a timestamp and no flag at all. Treating
        them as anything would have invented history."""
        assert _kind_of({"@osmId": "way/1", "@timestamp": "2020-01-01T00:00:00Z"}) is None

    def test_osm_id_splits(self) -> None:
        assert _split_osm_id("way/262058094") == ("way", "262058094")
        assert _split_osm_id("") == ("", "")


class TestSeries:
    """Counts must be net, and quiet months must still exist."""

    def test_deletion_reduces_the_count(self) -> None:
        events = [
            {
                "osm_type": "way",
                "osm_id": "1",
                "event_date": "2020-01-05",
                "event_kind": "creation",
                "state": "VA",
                "county_fips": "51107",
            },
            {
                "osm_type": "way",
                "osm_id": "1",
                "event_date": "2020-03-05",
                "event_kind": "deletion",
                "state": "VA",
                "county_fips": "51107",
            },
        ]
        rows = build(events, {("way", "1"): 1000.0})
        county = [r for r in rows if r["region_id"] == "county:51107"]
        assert county[0]["cumulative_count"] == 1
        assert county[-1]["cumulative_count"] == 0

    def test_tag_edits_do_not_move_the_count(self) -> None:
        """A mapper fixing a spelling does not build a data centre."""
        events = [
            {
                "osm_type": "way",
                "osm_id": "1",
                "event_date": "2020-01-05",
                "event_kind": "creation",
                "state": "VA",
                "county_fips": "51107",
            },
            {
                "osm_type": "way",
                "osm_id": "1",
                "event_date": "2020-02-05",
                "event_kind": "tag_change",
                "state": "VA",
                "county_fips": "51107",
            },
        ]
        rows = build(events, {})
        county = [r for r in rows if r["region_id"] == "county:51107"]
        assert {r["cumulative_count"] for r in county} == {1}

    def test_quiet_months_are_emitted(self) -> None:
        """Skipping empty months would compress time and make a pause in
        construction look like continuous growth."""
        events = [
            {
                "osm_type": "way",
                "osm_id": "1",
                "event_date": "2020-01-05",
                "event_kind": "creation",
                "state": "VA",
                "county_fips": "51107",
            },
            {
                "osm_type": "way",
                "osm_id": "2",
                "event_date": "2020-06-05",
                "event_kind": "creation",
                "state": "VA",
                "county_fips": "51107",
            },
        ]
        rows = build(events, {})
        county = [r for r in rows if r["region_id"] == "county:51107"]
        assert [r["period"] for r in county] == [
            "2020-01",
            "2020-02",
            "2020-03",
            "2020-04",
            "2020-05",
            "2020-06",
        ]

    def test_one_event_feeds_county_state_and_nation(self) -> None:
        events = [
            {
                "osm_type": "way",
                "osm_id": "1",
                "event_date": "2020-01-05",
                "event_kind": "creation",
                "state": "VA",
                "county_fips": "51107",
            }
        ]
        regions = {r["region_id"] for r in build(events, {})}
        assert regions == {"county:51107", "state:VA", "national:US"}

    def test_removal_without_an_observed_creation_is_ignored(self) -> None:
        """OpenStreetMap predates the history window, so an element can be
        created before it and deleted inside it. Counting that removal subtracts
        a facility the series never added; the national series really did read
        minus one data centre through 2012-2014 before this was fixed."""
        events = [
            {
                "osm_type": "way",
                "osm_id": "999",
                "event_date": "2013-04-05",
                "event_kind": "deletion",
                "state": "VA",
                "county_fips": "51107",
            }
        ]
        rows = build(events, {})
        assert all(int(r["cumulative_count"]) >= 0 for r in rows)

    def test_removal_after_an_observed_creation_still_counts(self) -> None:
        """The guard above must not silence genuine removals."""
        events = [
            {
                "osm_type": "way",
                "osm_id": "5",
                "event_date": "2019-01-05",
                "event_kind": "creation",
                "state": "VA",
                "county_fips": "51107",
            },
            {
                "osm_type": "way",
                "osm_id": "5",
                "event_date": "2019-05-05",
                "event_kind": "deletion",
                "state": "VA",
                "county_fips": "51107",
            },
        ]
        rows = [r for r in build(events, {}) if r["region_id"] == "county:51107"]
        assert rows[-1]["cumulative_count"] == 0

    def test_month_range_crosses_years(self) -> None:
        assert _month_range("2019-11", "2020-02") == [
            "2019-11",
            "2019-12",
            "2020-01",
            "2020-02",
        ]


class TestTiling:
    """Tiles overlap by construction, so the fetch must de-duplicate."""

    def test_tiles_cover_the_whole_box(self) -> None:
        box = BoundingBox(-10.0, 0.0, 10.0, 10.0)
        tiles = tile(box, 5.0)
        assert min(t.west for t in tiles) == pytest.approx(box.west)
        assert max(t.east for t in tiles) == pytest.approx(box.east)
        assert min(t.south for t in tiles) == pytest.approx(box.south)
        assert max(t.north for t in tiles) == pytest.approx(box.north)

    def test_adjacent_tiles_share_an_edge(self) -> None:
        """This is why de-duplication on the OSM id is mandatory: a building on
        the seam is returned by both neighbours."""
        tiles = tile(BoundingBox(0.0, 0.0, 10.0, 5.0), 5.0)
        assert tiles[0].east == pytest.approx(tiles[1].west)

    def test_us_tiles_reach_beyond_the_lower_48(self) -> None:
        labels = {name.rsplit("-", 1)[0] for name, _ in us_tiles(15.0)}
        assert {"conus", "alaska", "hawaii", "puerto-rico"} <= labels

    def test_tile_size_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            tile(BoundingBox(0.0, 0.0, 1.0, 1.0), 0.0)


class TestDeterministicWrites:
    """`git diff` is the change log, so writes must be byte-stable."""

    def test_same_rows_produce_identical_bytes(self, tmp_path: Path) -> None:
        rows = [{"a": "1", "b": "x"}, {"a": "2", "b": "y"}]
        first = tmp_path / "first.csv"
        second = tmp_path / "second.csv"
        write_csv(first, ("a", "b"), rows)
        write_csv(second, ("a", "b"), rows)
        assert first.read_bytes() == second.read_bytes()

    def test_line_endings_are_unix(self, tmp_path: Path) -> None:
        path = tmp_path / "out.csv"
        write_csv(path, ("a",), [{"a": "1"}])
        assert b"\r\n" not in path.read_bytes()
