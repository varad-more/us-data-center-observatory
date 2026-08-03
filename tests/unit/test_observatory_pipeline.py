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
from allocate_power import main as allocate_main  # noqa: E402
from assign_grid_regions import _accumulate, _blank_totals  # noqa: E402
from assign_grid_regions import build as grid_build  # noqa: E402
from assign_regions import _blank_region, _fold, _region_totals  # noqa: E402
from build_series import _month_range, build  # noqa: E402
from build_site_data import build_facilities, build_grid  # noqa: E402
from fetch_grid import VOLTAGE_PATTERN  # noqa: E402
from fetch_grid import capacity_mw as grid_capacity  # noqa: E402
from fetch_grid import max_voltage_v as grid_max_voltage  # noqa: E402
from fetch_grid import normalise as grid_normalise  # noqa: E402
from fetch_osm_history import _kind_of, _split_osm_id  # noqa: E402
from fetch_osm_snapshot import _ring_area_m2, normalise, site_class  # noqa: E402


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


class TestGridVoltage:
    """The voltage filter decides which substations exist as far as the map is
    concerned, and every way it can be wrong hides the largest ones."""

    def test_reads_the_highest_level_of_a_multi_voltage_substation(self) -> None:
        """OSM records a transforming substation as a list.

        A filter anchored to the whole tag matches none of these, and the ones
        it drops are the big multi-level yards the layer exists to show.
        """
        assert grid_max_voltage("115000;230000") == 230000
        assert grid_max_voltage("69000;138000;345000") == 345000

    def test_handles_a_single_value_and_stray_whitespace(self) -> None:
        assert grid_max_voltage("500000") == 500000
        assert grid_max_voltage(" 230000 ; 115000 ") == 230000

    def test_refuses_to_invent_a_number_from_free_text(self) -> None:
        """An unparseable tag is unknown, not zero, and not the threshold."""
        assert grid_max_voltage("high") is None
        assert grid_max_voltage("") is None
        assert grid_max_voltage(None) is None

    def test_keeps_the_numbers_out_of_a_mixed_tag(self) -> None:
        assert grid_max_voltage("115000;unknown") == 115000

    def test_server_regex_agrees_with_the_parser_on_lists(self) -> None:
        """The Overpass filter is an optimisation; if it excluded rows the
        parser would keep, the layer would be missing them before the parser
        ever ran."""
        import re

        pattern = re.compile(VOLTAGE_PATTERN)
        for value in ("115000;230000", "69000;138000;345000", "500000", "69000"):
            assert pattern.search(value), value
        for value in ("12000", "34500", "4160"):
            assert not pattern.search(value), value


class TestGridNormalise:
    """Rows that reach the map."""

    def test_drops_a_distribution_substation(self) -> None:
        row = grid_normalise(
            {
                "type": "way",
                "id": 1,
                "center": {"lat": 39.0, "lon": -77.0},
                "tags": {"power": "substation", "voltage": "12000"},
            }
        )
        assert row is None

    def test_keeps_a_transmission_substation_at_its_highest_voltage(self) -> None:
        row = grid_normalise(
            {
                "type": "way",
                "id": 2,
                "center": {"lat": 39.0, "lon": -77.0},
                "tags": {"power": "substation", "voltage": "115000;230000", "name": "Yard"},
            }
        )
        assert row is not None
        assert row["voltage_kv"] == 230.0
        assert row["kind"] == "substation"

    def test_drops_an_element_with_no_position(self) -> None:
        """A relation with no centre cannot be drawn; writing it at 0,0 would
        put a substation in the Atlantic."""
        row = grid_normalise(
            {"type": "relation", "id": 3, "tags": {"power": "substation", "voltage": "230000"}}
        )
        assert row is None

    def test_keeps_a_plant_regardless_of_voltage(self) -> None:
        """Generation is collected on being a plant, not on carrying a voltage
        tag - most plants do not."""
        row = grid_normalise(
            {
                "type": "relation",
                "id": 4,
                "center": {"lat": 36.0, "lon": -78.0},
                "tags": {
                    "power": "plant",
                    "plant:source": "nuclear",
                    "plant:output:electricity": "1900 MW",
                },
            }
        )
        assert row is not None
        assert row["kind"] == "plant"
        assert row["source"] == "nuclear"
        assert row["capacity_mw"] == 1900.0

    def test_ignores_a_generator(self) -> None:
        """power=generator is one turbine. Virginia alone has 22,854."""
        row = grid_normalise(
            {
                "type": "node",
                "id": 5,
                "lat": 36.0,
                "lon": -78.0,
                "tags": {"power": "generator", "generator:source": "solar"},
            }
        )
        assert row is None


class TestGridCapacity:
    """A capacity figure invented from free text would look reported."""

    def test_converts_the_units_that_actually_appear(self) -> None:
        assert grid_capacity("1900 MW") == 1900.0
        assert grid_capacity("1.2 GW") == 1200.0
        assert grid_capacity("500 kW") == 0.5

    def test_leaves_unparseable_output_blank(self) -> None:
        assert grid_capacity("about 2 reactors") is None
        assert grid_capacity("") is None

    def test_refuses_a_bare_number_too_large_to_be_megawatts(self) -> None:
        """`1200000000` is watts written without a unit. Read as MW it would
        publish a 1.2-billion-megawatt power station."""
        assert grid_capacity("1200000000") is None
        assert grid_capacity("250") == 250.0


class TestGridGeoJson:
    """The grid layer is ~42,000 points fetched over the network on demand, so
    what is left out of each feature decides whether it is fetchable at all."""

    def _row(self, **over: str) -> dict[str, str]:
        row = {
            "osm_type": "way",
            "osm_id": "1",
            "kind": "substation",
            "name": "",
            "operator": "",
            "voltage_kv": "230.0",
            "source": "",
            "capacity_mw": "",
            "lat": "38.123456789",
            "lon": "-77.987654321",
            "county_fips": "51107",
            "state": "VA",
        }
        row.update(over)
        return row

    def test_omits_tags_a_mapper_did_not_fill_in(self) -> None:
        """Blank strings for every absent tag would roughly double the file."""
        feature = build_grid([self._row()])["features"][0]
        assert set(feature["properties"]) == {"kind", "voltage_kv"}
        assert "name" not in feature["properties"]

    def test_rounds_coordinates_to_about_a_metre(self) -> None:
        """The sixth decimal places a substation no better than its own fence."""
        lon, lat = build_grid([self._row()])["features"][0]["geometry"]["coordinates"]
        assert lat == 38.12346
        assert lon == -77.98765

    def test_carries_numbers_as_numbers(self) -> None:
        """The map sizes circles from these; a string would break the paint
        expression silently and draw every asset at the floor radius."""
        props = build_grid(
            [self._row(kind="plant", voltage_kv="", capacity_mw="1900.0", source="nuclear")]
        )["features"][0]["properties"]
        assert props["capacity_mw"] == 1900.0
        assert isinstance(props["capacity_mw"], float)
        assert props["source"] == "nuclear"

    def test_skips_a_row_with_an_unusable_position(self) -> None:
        assert build_grid([self._row(lat="")])["features"] == []

    def test_leaves_out_assets_that_are_not_in_the_united_states(self) -> None:
        """The Overpass boxes this is fetched with reach into Sonora, Chihuahua,
        Ontario and the Gulf, and 2,898 of the 65,325 rows land outside every US
        county. Publishing them drew Mexican substations on a map captioned "the
        contiguous states" and counted them in a national total. An unassigned
        row is the only record that an asset is out of scope."""
        rows = [self._row(), self._row(osm_id="2", county_fips="", state="")]
        features = build_grid(rows)["features"]
        assert len(features) == 1

    def test_no_grid_data_is_a_valid_empty_layer(self) -> None:
        """The grid stage takes far longer than the rest of the pipeline, so the
        site has to build before it has ever run - and the map's fetch needs a
        valid empty collection rather than a 404 to interpret."""
        assert build_grid([]) == {"type": "FeatureCollection", "features": []}


class TestGridRegionTotals:
    """County grid summaries. Every field here can mislead a siting question if
    it folds an unknown into a number."""

    def _sub(self, kv: str, fips: str = "51107") -> dict[str, str]:
        return {"kind": "substation", "voltage_kv": kv, "county_fips": fips, "state": "VA"}

    def _plant(self, mw: str, fips: str = "51107") -> dict[str, str]:
        return {"kind": "plant", "capacity_mw": mw, "county_fips": fips, "state": "VA"}

    def test_separates_bulk_transmission_from_the_rest(self) -> None:
        """Forty 69 kV yards are not a substitute for one 500 kV substation, so
        a single count would rank counties backwards for a large load."""
        totals = _blank_totals()
        for row in (self._sub("69"), self._sub("115"), self._sub("230"), self._sub("500")):
            _accumulate(totals, row)
        assert totals["substation_count"] == 4
        assert totals["bulk_substation_count"] == 2
        assert totals["max_voltage_kv"] == 500.0

    def test_counts_a_plant_with_no_capacity_instead_of_summing_it_as_zero(self) -> None:
        """A county whose generation is simply untagged must not read as a
        county with none, so the unknowns are carried beside the total."""
        totals = _blank_totals()
        _accumulate(totals, self._plant("100"))
        _accumulate(totals, self._plant(""))
        _accumulate(totals, self._plant("not recorded"))
        assert totals["plant_count"] == 3
        assert totals["plant_capacity_mw"] == 100.0
        assert totals["plants_without_capacity"] == 2

    def test_a_substation_with_an_unparseable_voltage_is_not_bulk(self) -> None:
        totals = _blank_totals()
        _accumulate(totals, self._sub("high"))
        assert totals["substation_count"] == 1
        assert totals["bulk_substation_count"] == 0

    def test_an_asset_in_no_county_is_left_out_rather_than_guessed(self) -> None:
        """2,898 of 65,325 assets fall outside every US county - offshore, or
        across a border inside the query envelope. Attaching them to whichever
        county is nearest would invent grid capacity in a real place."""

        class _Index:
            properties = [{"fips": "51107", "name": "Loudoun County", "state": "VA"}]

        rows = grid_build(
            [self._sub("500"), self._sub("500", fips="")], _Index()  # type: ignore[arg-type]
        )
        county = next(r for r in rows if r["region_kind"] == "county")
        assert county["substation_count"] == 1

    def test_state_totals_include_every_county_in_them(self) -> None:
        class _Index:
            properties = [
                {"fips": "51107", "name": "Loudoun County", "state": "VA"},
                {"fips": "51153", "name": "Prince William County", "state": "VA"},
            ]

        rows = grid_build(
            [self._sub("500"), self._sub("230", fips="51153")], _Index()  # type: ignore[arg-type]
        )
        state = next(r for r in rows if r["region_kind"] == "state")
        assert state["substation_count"] == 2
        assert state["bulk_substation_count"] == 2


class TestSiteClass:
    """What an element's area measures decides whether it may carry a megawatt.

    The three data-centre tags are satisfied both by machine halls and by the
    land parcels campuses sit on. Pooling the two sent 82% of a measured national
    total to geometry that is not a building, and put a 3.1 km2 parcel in Racine
    County above every mapped building in Loudoun.
    """

    def test_building_tag_makes_it_a_building(self) -> None:
        assert site_class({"building": "yes"}, "way") == "building"
        assert site_class({"building": "data_center"}, "way") == "building"

    def test_building_no_is_not_a_building(self) -> None:
        """`building=no` states the area is *not* a building.

        Reading it as one put the 2 km2 Meta Los Lunas land parcel into the floor
        area pool and sent Valencia County, New Mexico to second in the nation on
        six elements.
        """
        assert site_class({"building": "no", "landuse": "industrial"}, "way") == "site"

    def test_landuse_without_building_is_a_site(self) -> None:
        """A campus boundary is land, not floor space."""
        assert site_class({"landuse": "industrial"}, "way") == "site"
        assert site_class({"telecom": "data_center"}, "way") == "site"

    def test_construction_is_not_operating(self) -> None:
        """Both spellings mappers use, because either one means "not yet built"."""
        assert site_class({"landuse": "construction"}, "way") == "construction"
        assert site_class({"building": "construction"}, "way") == "construction"

    def test_construction_wins_over_a_building_tag(self) -> None:
        """A shell under construction consumed none of a measured 2024 total."""
        assert site_class({"building": "yes", "landuse": "construction"}, "way") == "construction"

    def test_a_node_carries_no_area(self) -> None:
        assert site_class({"telecom": "data_center"}, "node") == "point"

    def test_normalise_records_the_class(self) -> None:
        """The column has to survive the fetch or nothing downstream can use it."""
        element = {
            "type": "way",
            "id": 7,
            "tags": {"landuse": "construction", "name": "Half-built"},
            "geometry": [
                {"lon": 0.0, "lat": 0.0},
                {"lon": 0.001, "lat": 0.0},
                {"lon": 0.001, "lat": 0.001},
                {"lon": 0.0, "lat": 0.001},
            ],
        }
        row = normalise(element)
        assert row is not None
        assert row["site_class"] == "construction"


class TestRegionClassTotals:
    """A region's areas are kept apart because they measure different things."""

    def _fold_all(self, *facilities: dict[str, str]) -> dict[str, object]:
        totals = _blank_region()
        for facility in facilities:
            _fold(totals, facility)
        return _region_totals(totals)

    def test_floor_area_excludes_land_and_construction(self) -> None:
        row = self._fold_all(
            {"footprint_m2": "10000", "site_class": "building"},
            {"footprint_m2": "3000000", "site_class": "site"},
            {"footprint_m2": "500000", "site_class": "construction"},
        )
        # The parcel is 300x the building; pooling would make the building
        # invisible and hand the region's whole allocation to a property line.
        assert row["footprint_m2"] == "10000.0"
        assert row["site_area_m2"] == "3000000.0"
        assert row["construction_area_m2"] == "500000.0"

    def test_every_facility_is_counted_exactly_once(self) -> None:
        """Excluded from the estimate is not excluded from the count."""
        row = self._fold_all(
            {"footprint_m2": "10000", "site_class": "building"},
            {"footprint_m2": "3000000", "site_class": "site"},
            {"footprint_m2": "500000", "site_class": "construction"},
            {"footprint_m2": "0", "site_class": "point"},
        )
        assert row["facility_count"] == 4
        assert row["building_count"] == 1
        assert row["site_count"] == 1
        assert row["construction_count"] == 1

    def test_a_node_is_not_counted_as_a_site(self) -> None:
        """Nodes have no area at all, so calling them parcels would misreport
        the reason a region carries no estimate for them."""
        row = self._fold_all({"footprint_m2": "0", "site_class": "point"})
        assert row["site_count"] == 0
        assert row["site_area_m2"] == "0.0"

    def test_an_unlabelled_area_is_not_assumed_to_be_a_building(self) -> None:
        """Rows predating `site_class` must not silently rejoin the floor pool."""
        row = self._fold_all({"footprint_m2": "40000"})
        assert row["footprint_m2"] == "0.0"
        assert row["site_area_m2"] == "40000.0"


class TestPowerAllocation:
    """The allocation is the site's central inferred number.

    LBNL's 192 TWh is measured consumption from data centres that ran in 2024.
    Handing a share of it to a construction site asserts that an unbuilt facility
    drew power - the same class of error as reading a mapping date as a build
    date, and the one this project exists to avoid.
    """

    def _run(self, tmp_path: Path, facilities: list[dict[str, str]]) -> list[dict[str, str]]:
        import csv

        facilities_path = tmp_path / "facilities.csv"
        regions_path = tmp_path / "regions.csv"
        national_path = tmp_path / "national.csv"
        out_path = tmp_path / "out.csv"

        write_csv(
            facilities_path,
            ("osm_type", "osm_id", "footprint_m2", "site_class", "state"),
            facilities,
        )
        # One state region holding the whole mapped stock, so its allocation must
        # come back as the entire national total.
        floor = sum(float(f["footprint_m2"]) for f in facilities if f["site_class"] == "building")
        write_csv(
            regions_path,
            ("region_id", "region_kind", "name", "state", "fips", "footprint_m2"),
            [
                {
                    "region_id": "state:VA",
                    "region_kind": "state",
                    "name": "VA",
                    "state": "VA",
                    "fips": "",
                    "footprint_m2": f"{floor:.1f}",
                }
            ],
        )
        write_csv(
            national_path,
            ("year", "electricity_twh", "water_bgal", "series_kind"),
            [
                {
                    "year": "2024",
                    "electricity_twh": "192",
                    "water_bgal": "17.4",
                    "series_kind": "historical",
                }
            ],
        )
        allocate_main(
            [
                "--facilities",
                str(facilities_path),
                "--regions",
                str(regions_path),
                "--national",
                str(national_path),
                "--out",
                str(out_path),
            ]
        )
        with out_path.open(encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_shares_sum_to_the_national_total(self, tmp_path: Path) -> None:
        """Conservation is the whole point of a calibrated allocation."""
        rows = self._run(
            tmp_path,
            [
                {
                    "osm_type": "way",
                    "osm_id": "1",
                    "footprint_m2": "10000",
                    "site_class": "building",
                    "state": "VA",
                },
                {
                    "osm_type": "way",
                    "osm_id": "2",
                    "footprint_m2": "30000",
                    "site_class": "building",
                    "state": "VA",
                },
            ],
        )
        # 192 TWh over 8760 h = 21,918 MW.
        assert float(rows[0]["est_mw"]) == pytest.approx(21918.0, abs=1.0)

    def test_a_land_parcel_does_not_dilute_the_buildings(self, tmp_path: Path) -> None:
        """A parcel 100x the building must not take 99% of the region's load.

        This is the defect exactly: one 3.1 km2 Racine County parcel drew 598 MW
        while every mapped building in Loudoun County together drew 1,020 MW.
        """
        rows = self._run(
            tmp_path,
            [
                {
                    "osm_type": "way",
                    "osm_id": "1",
                    "footprint_m2": "10000",
                    "site_class": "building",
                    "state": "VA",
                },
                {
                    "osm_type": "way",
                    "osm_id": "2",
                    "footprint_m2": "1000000",
                    "site_class": "site",
                    "state": "VA",
                },
            ],
        )
        assert float(rows[0]["est_mw"]) == pytest.approx(21918.0, abs=1.0)

    def test_a_construction_site_gets_nothing(self, tmp_path: Path) -> None:
        rows = self._run(
            tmp_path,
            [
                {
                    "osm_type": "way",
                    "osm_id": "1",
                    "footprint_m2": "10000",
                    "site_class": "building",
                    "state": "VA",
                },
                {
                    "osm_type": "way",
                    "osm_id": "2",
                    "footprint_m2": "900000",
                    "site_class": "construction",
                    "state": "VA",
                },
            ],
        )
        assert float(rows[0]["est_mw"]) == pytest.approx(21918.0, abs=1.0)


class TestFacilityPowerKeys:
    """The map layer and the region pages must agree on who has a figure."""

    def _properties(self, site_class: str) -> dict[str, object]:
        collection = build_facilities(
            [
                {
                    "osm_type": "way",
                    "osm_id": "1",
                    "lon": "-77.5",
                    "lat": "39.0",
                    "footprint_m2": "10000",
                    "site_class": site_class,
                }
            ],
            national_mw=21918.0,
            total_area=10000.0,
        )
        return collection["features"][0]["properties"]

    def test_a_building_carries_a_power_figure(self) -> None:
        assert self._properties("building")["est_mw"] == pytest.approx(21918.0, abs=1.0)

    def test_a_parcel_carries_no_power_key_at_all(self) -> None:
        """Absent reads as unknown; a zero would read as a measured nothing."""
        properties = self._properties("site")
        assert "est_mw" not in properties
        assert properties["site_class"] == "site"

    def test_a_construction_site_carries_no_power_key(self) -> None:
        assert "est_mw" not in self._properties("construction")
