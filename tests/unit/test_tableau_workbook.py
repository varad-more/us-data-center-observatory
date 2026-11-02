"""Tests for the generated Tableau workbook.

Tableau's published schema validates structure only, and a workbook that passes
it can still fail to load. What breaks a generated workbook in practice is a
reference to something that does not exist: a shelf naming a field its data
source never declared, a formula naming a column, a dashboard zone naming a
sheet. Tableau reports each of those only once the workbook is open in front of
a reader, so they are checked here instead.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "observatory"
sys.path.insert(0, str(SCRIPTS))

import build_tableau_workbook as wb  # noqa: E402

pytestmark = pytest.mark.unit

USER = "{http://www.tableausoftware.com/xml/user}"


@pytest.fixture(scope="module")
def root() -> ET.Element:
    return wb.build_workbook().getroot()


def _source_columns(root: ET.Element) -> dict[str, set[str]]:
    """Every column each top-level data source declares."""
    return {
        ds.get("name", ""): {c.get("name", "") for c in ds.findall("column")}
        for ds in root.find("datasources")  # type: ignore[union-attr]
    }


def test_every_column_the_workbook_reads_is_in_its_csv() -> None:
    assert wb.check_headers() == []


def test_the_workbook_is_deterministic() -> None:
    """The XML is the reviewable half of the package, so a rebuild with no data
    change must not produce a diff."""
    assert wb.workbook_bytes(wb.build_workbook()) == wb.workbook_bytes(wb.build_workbook())


def test_it_is_written_in_the_dialect_tableau_public_loads(root: ET.Element) -> None:
    """Each of these validates against Tableau's 2026.2 schema and makes Tableau
    Public 2026.3 abandon the load before reading any data. Found by bisection
    against the app's own log."""
    assert root.get("version") == "18.1"
    assert root.find("document-format-change-manifest") is None
    assert root.find("explain-data") is None
    for ds in root.iter("datasource"):
        assert ds.find("layout") is None


def test_every_data_source_is_an_extract(root: ET.Element) -> None:
    """Tableau Public refuses a live file connection outright."""
    for ds in wb.DATASOURCES:
        el = root.find(f"datasources/datasource[@name='{ds.name}']")
        assert el is not None
        conn = el.find("connection/named-connections/named-connection/connection")
        assert conn is not None and conn.get("class") == "hyper"
        assert conn.get("dbname") == f"{wb.PACKAGE_DATA_DIR}/{ds.name}.hyper"
        relation = el.find("connection/relation")
        assert relation is not None and relation.get("table") == "[Extract].[Extract]"


def test_every_formula_names_a_field_its_source_has(root: ET.Element) -> None:
    declared = _source_columns(root)
    for ds in root.find("datasources"):  # type: ignore[union-attr]
        for col in ds.findall("column"):
            calc = col.find("calculation")
            if calc is None:
                continue
            formula = calc.get("formula", "")
            for source, name in re.findall(r"(?:\[([^\[\]]+)\]\.)?\[([^\[\]]+)\]", formula):
                owner = source or ds.get("name", "")
                assert f"[{name}]" in declared[owner], (col.get("name"), formula)


def test_every_shelf_names_a_declared_instance_of_a_declared_field(root: ET.Element) -> None:
    """The failure Tableau draws as a red pill: a sheet using a field, or an
    aggregation of a field, that its data source does not provide."""
    declared = _source_columns(root)
    for sheet in root.iter("worksheet"):
        view = sheet.find("table/view")
        assert view is not None
        instances: dict[str, set[str]] = {}
        for deps in view.findall("datasource-dependencies"):
            source = deps.get("datasource", "")
            for col in deps.findall("column"):
                assert col.get("name") in declared[source], (sheet.get("name"), col.get("name"))
            names = set()
            for inst in deps.findall("column-instance"):
                assert inst.get("column") in {c.get("name") for c in deps.findall("column")}
                names.add(inst.get("name", ""))
            instances[source] = names

        text = ET.tostring(sheet, encoding="unicode")
        for source, name in re.findall(r"\[([a-z_]+)\]\.(\[[a-z]+:[^\]]+:[nqo]k\])", text):
            assert name in instances.get(source, set()), (sheet.get("name"), source, name)


def test_every_zone_and_window_names_a_real_sheet(root: ET.Element) -> None:
    sheets = {s.get("name") for s in root.iter("worksheet")}
    dashboards = {d.get("name") for d in root.iter("dashboard")}
    for dash in root.iter("dashboard"):
        for zone in dash.iter("zone"):
            if zone.get("name") is not None:
                assert zone.get("name") in sheets, (dash.get("name"), zone.get("name"))
    windows = root.find("windows")
    assert windows is not None
    named = {w.get("name") for w in windows}
    assert named == sheets | dashboards
    hidden = {w.get("name") for w in windows if w.get("hidden") == "true"}
    assert hidden == sheets, "every worksheet sits inside a dashboard tab"


def test_a_removal_is_never_worded_as_a_demolition() -> None:
    labels = {kind: label for kind, label, _ in wb.EVENT_LABELS}
    assert labels["deletion"] == "Removed from OpenStreetMap"
    for _, label, _ in wb.EVENT_LABELS:
        assert not re.search(r"demolish|closed|shut|decommission", label, re.IGNORECASE)


@pytest.mark.parametrize(
    ("field", "guard"),
    [
        # A point has no geometry; its 0.0 in the CSV is "nothing mapped".
        ("Mapped area m2", '[site_class] = "point" THEN NULL'),
        # No mapped building means nothing to allocate to: no estimate, not 0 MW.
        ("Estimated MW", "[building_count] > 0"),
        ("Estimated water", "[building_count] > 0"),
        ("Max voltage kV", "[substation_count] > 0"),
        # Every plant untagged means the capacity is unknown, not zero.
        ("Tagged plant capacity MW", "[plant_count] > [plants_without_capacity]"),
    ],
)
def test_an_unknown_is_null_not_zero(field: str, guard: str) -> None:
    formulas = {f.name: f.formula for ds in wb.DATASOURCES for f in ds.calcs}
    assert guard in (formulas[field] or "")


def test_every_megawatt_figure_says_it_is_inferred() -> None:
    for ds in wb.DATASOURCES:
        for f in ds.fields().values():
            if "MW" in f.caption and f.formula is not None and f.datatype == "real":
                assert "inferred" in f.caption or "tagged" in f.caption, f.caption


def test_an_empty_cell_reaches_the_extract_as_null() -> None:
    assert wb._typed("", "real") is None
    assert wb._typed("", "string") is None
    assert wb._typed("0.0", "real") == 0.0
    # A FIPS code keeps its leading zero.
    assert wb._typed("01069", "string") == "01069"


def test_the_grid_join_keeps_every_region(tmp_path: Path) -> None:
    """A left join: a region the grid file lacks keeps its row, with nulls."""
    (tmp_path / "regions.csv").write_text(
        "region_id,region_kind,name,state,fips,facility_count,building_count,site_count,"
        "construction_count,footprint_m2,site_area_m2,construction_area_m2,"
        "share_of_footprint,est_mw,est_gal_per_day\n"
        "county:51107,county,Loudoun County,VA,51107,1,1,0,0,10.0,0.0,0.0,1.0,5.0,10\n"
        "county:99999,county,Nowhere County,ZZ,99999,1,1,0,0,10.0,0.0,0.0,1.0,5.0,10\n"
    )
    (tmp_path / "grid_regions.csv").write_text(
        "region_id,region_kind,name,state,fips,substation_count,bulk_substation_count,"
        "max_voltage_kv,plant_count,plant_capacity_mw,plants_without_capacity\n"
        "county:51107,county,Loudoun County,VA,51107,67,64,500.0,1,778.0,0\n"
    )
    rows = wb.extract_rows(wb.REGIONS, tmp_path)
    assert len(rows) == 2
    width = len(wb.REGIONS.columns())
    assert all(len(r) == width for r in rows)
    assert rows[0][-6:] == (67, 64, 500.0, 1, 778.0, 0)
    assert rows[1][-6:] == (None,) * 6
