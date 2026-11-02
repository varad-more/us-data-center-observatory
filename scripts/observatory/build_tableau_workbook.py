#!/usr/bin/env python3
"""Build the Tableau workbook that presents the observatory dataset.

Writes ``tableau/us-data-center-observatory.twbx``: a packaged workbook holding
the workbook definition and one Hyper extract per data source, built from the
committed CSVs, so it opens in Tableau Desktop or Tableau Public with nothing
else on disk. Extracts rather than the CSVs themselves because Tableau Public
refuses a live file connection ("Workbooks saved to Tableau Public must use
extracts"); each source connects to its extract the way the sample data source
Tableau Public ships with does.

The workbook is generated rather than saved out of Tableau so it follows from
the committed CSVs and can be rebuilt after every poll with one command. The
workbook XML is deterministic and tested. The package is not byte-stable,
because a Hyper file carries ids that differ between runs, so it is rebuilt by
hand (``make tableau``) like the share card, not by the CI drift gate.

The project's rules carry over into the workbook as calculated fields. A Tableau
default would quietly break each of them:

* **An unknown is never a zero.** A point record has no geometry, so its area is
  null rather than the 0.0 in the CSV. A county with no mapped building gets no
  megawatt estimate rather than 0 MW. A county whose power plants carry no
  capacity tag gets no capacity rather than 0 MW.
* **An inferred value never reads like a reported one.** Every megawatt figure
  is captioned as inferred, and the national electricity chart marks reported
  history and predicted scenarios with different shapes.
* **A removal is not a demolition.** OpenStreetMap deletions read "Removed from
  OpenStreetMap".
* **A date is when the map recorded a facility, not when it was built.** The
  growth chart says so, and shades the years before the tag was in common use.

Run::

    python scripts/observatory/build_tableau_workbook.py
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from _common import DATA_DIR, REPO_ROOT, read_csv, state_name

OUT_PATH = REPO_ROOT / "tableau" / "us-data-center-observatory.twbx"
TWB_NAME = "us-data-center-observatory.twb"
# Where the extracts sit inside the package, relative to its root.
PACKAGE_DATA_DIR = "Data/Extracts"

USER_NS = "http://www.tableausoftware.com/xml/user"
ET.register_namespace("user", USER_NS)

# The document format of the sample workbook Tableau ships inside the app
# (Contents/install/Performance/PerformanceRecording_new.twb), which Tableau
# upgrades on open. Every element here follows that file's dialect.
#
# Tableau's published 2026.2 schema describes a newer dialect - `26.2` with
# <ManifestByVersion/>, <explain-data>, <computed-sort>, zone `type-v2` - and a
# document written that way validates against the schema and still fails to
# load: Tableau Public 2026.3 rejects the 26.x envelope, the manifest and
# <explain-data> each on their own, in its DOM loader, before reading any data.
WORKBOOK_VERSION = "18.1"

# A zip entry's timestamp is part of its bytes. Pinning it keeps wall-clock
# time out of the package.
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

# The site's three pen inks and its muted ink, so the workbook and the website
# read as one publication.
PEN_RED = "#b03a26"
PEN_BLUE = "#4a4ebf"
PEN_GREEN = "#0f7a55"
INK = "#232420"
INK_MUTED = "#8c8d84"

# The growth chart's region picker. Its members come from the data; its name
# does not, so the calculated field that reads it can be declared statically.
PARAMETER_NAME = "Parameter 1"

DASHBOARD_WIDTH = 1200
DASHBOARD_HEIGHT = 900


def _attr(name: str) -> str:
    """Qualify an attribute in Tableau's ``user:`` namespace."""
    return f"{{{USER_NS}}}{name}"


# --------------------------------------------------------------- data model --


@dataclass(frozen=True)
class Field:
    """A column a sheet can use: a CSV column or a calculated field.

    ``name`` is the internal name formulas and shelves refer to, so it is kept
    to plain ASCII. ``caption`` is what Tableau shows.
    """

    name: str
    datatype: str  # string | integer | real | date | boolean
    caption: str
    role: str  # dimension | measure
    type: str  # nominal | ordinal | quantitative
    formula: str | None = None
    semantic_role: str | None = None
    default_format: str | None = None
    aggregation: str | None = None
    aliases: tuple[tuple[str, str], ...] = ()

    @property
    def ref(self) -> str:
        return f"[{self.name}]"


def _default_type(datatype: str) -> str:
    """Tableau's own defaults: numbers are quantitative, dates ordinal, text and
    booleans nominal."""
    if datatype in ("integer", "real"):
        return "quantitative"
    return "ordinal" if datatype == "date" else "nominal"


def raw(
    name: str,
    datatype: str,
    caption: str,
    *,
    role: str | None = None,
    type_: str | None = None,
    semantic_role: str | None = None,
    default_format: str | None = None,
    aliases: tuple[tuple[str, str], ...] = (),
) -> Field:
    """A column read straight from a CSV.

    Numbers default to measures, text and dates to dimensions - the same choice
    Tableau would make - but every column is declared, because a declared type
    is what stops ``01069`` being read as the integer 1069.
    """
    numeric = datatype in ("integer", "real")
    return Field(
        name=name,
        datatype=datatype,
        caption=caption,
        role=role or ("measure" if numeric else "dimension"),
        type=type_ or _default_type(datatype),
        semantic_role=semantic_role,
        default_format=default_format,
        aggregation="Sum" if numeric else None,
        aliases=aliases,
    )


def calc(
    name: str,
    datatype: str,
    caption: str,
    formula: str,
    *,
    role: str | None = None,
    type_: str | None = None,
    default_format: str | None = None,
) -> Field:
    """A calculated field."""
    numeric = datatype in ("integer", "real")
    return Field(
        name=name,
        datatype=datatype,
        caption=caption,
        role=role or ("measure" if numeric else "dimension"),
        type=type_ or _default_type(datatype),
        formula=formula,
        default_format=default_format,
    )


@dataclass(frozen=True)
class Table:
    """A CSV file and the columns the workbook takes from it."""

    filename: str
    columns: tuple[Field, ...]


@dataclass(frozen=True)
class DataSource:
    """One extract. ``tables[1:]`` are left-joined onto ``tables[0]`` on
    ``join_key``, which every table carries and only the first contributes."""

    name: str
    caption: str
    tables: tuple[Table, ...]
    calcs: tuple[Field, ...] = ()
    join_key: str | None = None
    # field name -> ((value, colour), ...)
    palettes: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()

    @property
    def connection(self) -> str:
        return f"hyper.{self.name}"

    def columns(self) -> tuple[Field, ...]:
        """The extract's columns, in order."""
        return tuple(c for table in self.tables for c in table.columns)

    def fields(self) -> dict[str, Field]:
        out = {c.name: c for c in self.columns()}
        for c in self.calcs:
            out[c.name] = c
        return out


@dataclass(frozen=True)
class Parameter:
    name: str
    caption: str
    default: str
    members: tuple[tuple[str, str], ...]  # (value, alias)

    @property
    def ref(self) -> str:
        return f"[{self.name}]"


DERIVATION_PREFIX = {
    "None": "none",
    "Sum": "sum",
    "Avg": "avg",
    "CountD": "ctd",
    "Attribute": "attr",
}
TYPE_SUFFIX = {"nominal": "nk", "ordinal": "ok", "quantitative": "qk"}


@dataclass(frozen=True)
class Use:
    """A field placed on a shelf with an aggregation: a column instance."""

    ds: DataSource
    field: str
    derivation: str = "None"
    type: str | None = None

    @property
    def field_def(self) -> Field:
        return self.ds.fields()[self.field]

    @property
    def instance_type(self) -> str:
        if self.type:
            return self.type
        if self.derivation in ("Sum", "Avg", "CountD"):
            return "quantitative"
        return self.field_def.type

    @property
    def instance(self) -> str:
        prefix = DERIVATION_PREFIX[self.derivation]
        return f"[{prefix}:{self.field}:{TYPE_SUFFIX[self.instance_type]}]"

    @property
    def qualified(self) -> str:
        return f"[{self.ds.name}].{self.instance}"


@dataclass(frozen=True)
class Filter:
    use: Use
    members: tuple[str, ...]  # formula literals: '"state"', 'true'


@dataclass(frozen=True)
class Sheet:
    name: str
    title: str
    ds: DataSource
    mark: str
    rows: tuple[Use, ...] = ()
    cols: tuple[Use, ...] = ()
    color: Use | None = None
    shape: Use | None = None
    text: Use | None = None
    detail: tuple[Use, ...] = ()
    tooltip: tuple[str | Use, ...] = ()
    label: tuple[str | Use, ...] = ()
    show_labels: bool = False
    filters: tuple[Filter, ...] = ()
    sort: tuple[Use, Use, str] | None = None  # (dimension, by measure, direction)
    parameters: tuple[Parameter, ...] = ()
    fit: str | None = None  # entire | width


# ------------------------------------------------------------ the data model --

SITE_CLASS_ALIASES = (
    ("building", "Building (floor plate mapped)"),
    ("construction", "Under construction"),
    ("point", "Point (no geometry)"),
    ("site", "Campus land parcel"),
)

FACILITIES = DataSource(
    name="facilities",
    caption="Facilities",
    tables=(
        Table(
            "facilities.csv",
            (
                raw("osm_type", "string", "OSM element type"),
                raw("osm_id", "string", "OSM id"),
                raw("name", "string", "Name"),
                raw("operator", "string", "Operator"),
                raw("operator_wikidata", "string", "Operator (Wikidata)"),
                raw("ref", "string", "Ref"),
                raw(
                    "lat",
                    "real",
                    "Latitude",
                    semantic_role="[Geographical].[Latitude]",
                ),
                raw(
                    "lon",
                    "real",
                    "Longitude",
                    semantic_role="[Geographical].[Longitude]",
                ),
                raw("footprint_m2", "real", "Area in CSV (m², 0 = none mapped)"),
                raw("site_class", "string", "Site class", aliases=SITE_CLASS_ALIASES),
                raw("county_fips", "string", "County FIPS"),
                raw("state", "string", "State", semantic_role="[State].[Name]"),
                raw("first_seen", "date", "First seen in OpenStreetMap"),
            ),
        ),
    ),
    calcs=(
        calc("Facilities", "integer", "Facilities", "1", default_format="n#,##0"),
        calc(
            "Buildings",
            "integer",
            "Buildings",
            'IF [site_class] = "building" THEN 1 ELSE 0 END',
            default_format="n#,##0",
        ),
        calc(
            "Under construction",
            "integer",
            "Under construction",
            'IF [site_class] = "construction" THEN 1 ELSE 0 END',
            default_format="n#,##0",
        ),
        calc(
            "Facility label",
            "string",
            "Facility",
            'IF ISNULL([name]) OR [name] = "" THEN "(unnamed in OpenStreetMap)" ELSE [name] END',
        ),
        calc(
            "Operator label",
            "string",
            "Operator",
            'IF ISNULL([operator]) OR [operator] = "" THEN "not recorded" ELSE [operator] END',
        ),
        calc(
            "Mapped area m2",
            "real",
            "Mapped area (m²)",
            # A point has no geometry: the CSV's 0.0 means "nothing mapped",
            # not "zero square metres".
            'IF [site_class] = "point" THEN NULL ELSE ROUND([footprint_m2], 0) END',
            default_format="n#,##0",
        ),
        calc(
            "Area measures",
            "string",
            "What the area measures",
            'CASE [site_class] WHEN "building" THEN "the building\'s floor plate" '
            'WHEN "site" THEN "campus land, not floor area" '
            'WHEN "construction" THEN "land being built on, not floor area" '
            'ELSE "nothing: no geometry is mapped" END',
        ),
        calc(
            "First seen label",
            "string",
            "First seen in OpenStreetMap",
            # Null means no creation event in the retained window: mapped before
            # it began in 2012, or after its latest edit, which lags the
            # facility snapshot. "Before 2012" alone would be false for the
            # second kind.
            'IF ISNULL([first_seen]) THEN "not in the retained edit history: '
            'mapped before 2012 or after it ends" ELSE STR([first_seen]) END',
        ),
    ),
    palettes=(
        (
            "site_class",
            (
                ("building", PEN_RED),
                ("construction", PEN_GREEN),
                ("point", INK_MUTED),
                ("site", PEN_BLUE),
            ),
        ),
    ),
)

REGIONS = DataSource(
    name="regions",
    caption="Regions and grid",
    tables=(
        Table(
            "regions.csv",
            (
                raw("region_id", "string", "Region id"),
                raw("region_kind", "string", "Region kind"),
                raw("name", "string", "Region"),
                raw("state", "string", "State", semantic_role="[State].[Name]"),
                raw("fips", "string", "County FIPS"),
                raw("facility_count", "integer", "Facilities", default_format="n#,##0"),
                raw("building_count", "integer", "Buildings", default_format="n#,##0"),
                raw("site_count", "integer", "Campus land parcels", default_format="n#,##0"),
                raw(
                    "construction_count",
                    "integer",
                    "Under construction",
                    default_format="n#,##0",
                ),
                raw("footprint_m2", "real", "Building floor area (m²)", default_format="n#,##0"),
                raw("site_area_m2", "real", "Campus land area (m²)", default_format="n#,##0"),
                raw(
                    "construction_area_m2",
                    "real",
                    "Construction land area (m²)",
                    default_format="n#,##0",
                ),
                raw("share_of_footprint", "real", "Share of national floor area"),
                raw("est_mw", "real", "est_mw (CSV, 0 where nothing to allocate)"),
                raw("est_gal_per_day", "real", "est_gal_per_day (CSV)"),
            ),
        ),
        Table(
            "grid_regions.csv",
            (
                raw("substation_count", "integer", "Substations ≥ 69 kV", default_format="n#,##0"),
                raw(
                    "bulk_substation_count",
                    "integer",
                    "Substations ≥ 230 kV",
                    default_format="n#,##0",
                ),
                raw("max_voltage_kv", "real", "max_voltage_kv (CSV, 0 where no substation)"),
                raw("plant_count", "integer", "Power plants", default_format="n#,##0"),
                raw("plant_capacity_mw", "real", "plant_capacity_mw (CSV, tagged plants only)"),
                raw(
                    "plants_without_capacity",
                    "integer",
                    "Plants with no capacity tag",
                    default_format="n#,##0",
                ),
            ),
        ),
    ),
    join_key="region_id",
    calcs=(
        calc(
            "Estimated MW",
            "real",
            "Estimated MW (inferred)",
            # The site's own rule: a region with no mapped building has nothing
            # to allocate to, and that is "not estimated", not 0 MW.
            "IF [building_count] > 0 AND [est_mw] > 0 THEN ROUND([est_mw], 0) END",
            default_format="n#,##0",
        ),
        calc(
            "Estimated water",
            "real",
            "Estimated water, gal/day (inferred)",
            "IF [building_count] > 0 AND [est_gal_per_day] > 0 THEN [est_gal_per_day] END",
            default_format="n#,##0",
        ),
        calc(
            "Has MW estimate",
            "boolean",
            "Has an MW estimate",
            "NOT ISNULL([Estimated MW])",
        ),
        calc(
            "County label",
            "string",
            "County",
            '[name] + ", " + [state]',
        ),
        calc(
            "Max voltage kV",
            "real",
            "Highest substation voltage (kV)",
            "IF [substation_count] > 0 THEN [max_voltage_kv] END",
            default_format="n#,##0",
        ),
        calc(
            "Tagged plant capacity MW",
            "real",
            "Plant capacity where tagged (MW)",
            # All plants untagged means the capacity is unknown, not zero.
            "IF [plant_count] > [plants_without_capacity] THEN ROUND([plant_capacity_mw], 0) END",
            default_format="n#,##0",
        ),
    ),
)

SERIES = DataSource(
    name="region_series",
    caption="Mapped facilities over time",
    tables=(
        Table(
            "region_series.csv",
            (
                raw("region_id", "string", "Region id"),
                raw("period", "string", "Period"),
                raw(
                    "cumulative_count",
                    "integer",
                    "Facilities on the map",
                    default_format="n#,##0",
                ),
                raw("net_change", "integer", "Net change", default_format="n#,##0"),
                raw(
                    "cumulative_footprint_m2",
                    "real",
                    "Mapped area (m²)",
                    default_format="n#,##0",
                ),
            ),
        ),
    ),
    calcs=(
        calc(
            "Selected region count",
            "integer",
            "Facilities on the map",
            f"IF [region_id] = [Parameters].[{PARAMETER_NAME}] THEN [cumulative_count] END",
            default_format="n#,##0",
        ),
        calc(
            "Month",
            "date",
            "Month",
            "MAKEDATE(INT(LEFT([period], 4)), INT(RIGHT([period], 2)), 1)",
        ),
        calc(
            "Era",
            "string",
            "Mapping era",
            'IF [Month] < #2017-01-01# THEN "Before 2017: tag still being adopted" '
            'ELSE "2017 onward" END',
        ),
    ),
    palettes=(
        (
            "Era",
            (
                ("Before 2017: tag still being adopted", INK_MUTED),
                ("2017 onward", PEN_RED),
            ),
        ),
    ),
)

EVENT_LABELS = (
    ("creation", "Added to OpenStreetMap", PEN_GREEN),
    ("tag_change", "Tags edited", PEN_BLUE),
    ("geometry_change", "Outline edited", INK_MUTED),
    # Never "demolished" or "closed": a mapper retagging a building is
    # indistinguishable from the building coming down.
    ("deletion", "Removed from OpenStreetMap", PEN_RED),
)

EVENTS = DataSource(
    name="events",
    caption="OpenStreetMap edits",
    tables=(
        Table(
            "events.csv",
            (
                raw("osm_type", "string", "OSM element type"),
                raw("osm_id", "string", "OSM id"),
                raw("event_date", "date", "Edit date"),
                raw("event_kind", "string", "Edit kind (CSV)"),
                raw("lat", "real", "Latitude", semantic_role="[Geographical].[Latitude]"),
                raw("lon", "real", "Longitude", semantic_role="[Geographical].[Longitude]"),
                raw("county_fips", "string", "County FIPS"),
                raw("state", "string", "State", semantic_role="[State].[Name]"),
            ),
        ),
    ),
    calcs=(
        calc("Edits", "integer", "Edits", "1", default_format="n#,##0"),
        calc(
            "Year",
            "integer",
            "Year",
            "YEAR([event_date])",
            role="dimension",
            type_="ordinal",
            default_format="*0",
        ),
        calc(
            "Edit kind",
            "string",
            "Edit kind",
            "CASE [event_kind] "
            + " ".join(f'WHEN "{k}" THEN "{label}"' for k, label, _ in EVENT_LABELS)
            + " END",
        ),
    ),
    palettes=(("Edit kind", tuple((label, colour) for _, label, colour in EVENT_LABELS)),),
)

ENERGY = DataSource(
    name="national_energy",
    caption="National electricity (LBNL)",
    tables=(
        Table(
            "national_energy.csv",
            (
                raw(
                    "year",
                    "integer",
                    "Year",
                    role="dimension",
                    type_="quantitative",
                    default_format="*0",
                ),
                raw("electricity_twh", "real", "Electricity (TWh)", default_format="n#,##0"),
                raw("water_bgal", "real", "Water (billion gallons)"),
                raw("series_kind", "string", "Series kind"),
                raw("scenario", "string", "Scenario"),
                raw("assertion_class", "string", "Assertion class"),
                raw("source", "string", "Source"),
            ),
        ),
    ),
    calcs=(
        calc(
            "Series",
            "string",
            "Series",
            'IF [series_kind] = "historical" THEN "Reported: historical estimate" '
            'ELSE "Predicted: " + [scenario] + " scenario" END',
        ),
    ),
    palettes=(
        (
            "Series",
            (
                ("Reported: historical estimate", INK),
                ("Predicted: low scenario", PEN_GREEN),
                ("Predicted: reference scenario", PEN_BLUE),
                ("Predicted: high scenario", PEN_RED),
            ),
        ),
    ),
)

DATASOURCES = (FACILITIES, REGIONS, SERIES, EVENTS, ENERGY)


# ---------------------------------------------------------------- the sheets --


def u(ds: DataSource, name: str, derivation: str = "None", type_: str | None = None) -> Use:
    return Use(ds, name, derivation, type_)


def build_parameter(series_rows: list[dict[str, str]]) -> Parameter:
    """The region picker for the growth chart: the nation, then every state
    that has a series, named rather than coded."""
    states = sorted(
        {r["region_id"] for r in series_rows if r["region_id"].startswith("state:")},
        key=lambda rid: state_name(rid.split(":", 1)[1]),
    )
    members = (
        ("national:US", "United States"),
        *((rid, state_name(rid.split(":", 1)[1])) for rid in states),
    )
    return Parameter(PARAMETER_NAME, "Region", "national:US", members)


def build_sheets(param: Parameter) -> tuple[Sheet, ...]:
    fac, reg, ser, evt, nrg = FACILITIES, REGIONS, SERIES, EVENTS, ENERGY
    state_rows = Filter(u(reg, "region_kind"), ('"state"',))
    county_rows = Filter(u(reg, "region_kind"), ('"county"',))
    has_mw = Filter(u(reg, "Has MW estimate"), ("true",))
    facility_tooltip: tuple[str | Use, ...] = (
        u(fac, "Facility label"),
        "\nOperator: ",
        u(fac, "Operator label"),
        "\nRecorded as: ",
        u(fac, "site_class"),
        "\nMapped area: ",
        u(fac, "Mapped area m2", "Sum"),
        " m², which measures ",
        u(fac, "Area measures"),
        "\nFirst seen in OpenStreetMap: ",
        u(fac, "First seen label"),
        "\nState: ",
        u(fac, "state"),
        "   County FIPS: ",
        u(fac, "county_fips"),
        "\nOSM ",
        u(fac, "osm_type"),
        " ",
        u(fac, "osm_id"),
    )

    def kpi(name: str, measure: Use, caption: str) -> Sheet:
        return Sheet(
            name=name,
            title=name,
            ds=measure.ds,
            mark="Text",
            text=measure,
            label=(measure, f"\n{caption}"),
            show_labels=True,
        )

    return (
        Sheet(
            name="Facility map",
            title="Every data centre OpenStreetMap records in the United States",
            ds=fac,
            mark="Circle",
            rows=(u(fac, "lat", "Avg"),),
            cols=(u(fac, "lon", "Avg"),),
            color=u(fac, "site_class"),
            detail=(u(fac, "osm_type"), u(fac, "osm_id")),
            tooltip=facility_tooltip,
        ),
        kpi("KPI facilities", u(fac, "Facilities", "Sum"), "data centres mapped"),
        kpi("KPI buildings", u(fac, "Buildings", "Sum"), "mapped as buildings"),
        kpi(
            "KPI construction", u(fac, "Under construction", "Sum"), "mapped as under construction"
        ),
        kpi("KPI counties", u(fac, "county_fips", "CountD"), "counties with at least one"),
        Sheet(
            name="Facilities by state",
            title="Facilities by state, by what was mapped",
            ds=fac,
            mark="Bar",
            rows=(u(fac, "state"),),
            cols=(u(fac, "Facilities", "Sum"),),
            color=u(fac, "site_class"),
            tooltip=(
                u(fac, "state"),
                ": ",
                u(fac, "Facilities", "Sum"),
                " recorded as ",
                u(fac, "site_class"),
            ),
            sort=(u(fac, "state"), u(fac, "Facilities", "Sum"), "DESC"),
        ),
        Sheet(
            name="State allocation",
            title="Estimated MW by state (inferred)",
            ds=reg,
            mark="Bar",
            rows=(u(reg, "name"),),
            cols=(u(reg, "Estimated MW", "Sum"),),
            text=u(reg, "Estimated MW", "Sum"),
            show_labels=True,
            filters=(state_rows, has_mw),
            sort=(u(reg, "name"), u(reg, "Estimated MW", "Sum"), "DESC"),
            tooltip=(
                u(reg, "name"),
                "\nEstimated MW (inferred): ",
                u(reg, "Estimated MW", "Sum"),
                "\nEstimated water (inferred): ",
                u(reg, "Estimated water", "Sum"),
                " gal/day\nFacilities: ",
                u(reg, "facility_count", "Sum"),
                ", of which buildings: ",
                u(reg, "building_count", "Sum"),
            ),
        ),
        Sheet(
            name="County allocation",
            title="Estimated MW by county (inferred)",
            ds=reg,
            mark="Bar",
            rows=(u(reg, "County label"),),
            cols=(u(reg, "Estimated MW", "Sum"),),
            text=u(reg, "Estimated MW", "Sum"),
            show_labels=True,
            filters=(county_rows, has_mw),
            sort=(u(reg, "County label"), u(reg, "Estimated MW", "Sum"), "DESC"),
            tooltip=(
                u(reg, "County label"),
                "\nEstimated MW (inferred): ",
                u(reg, "Estimated MW", "Sum"),
                "\nFacilities: ",
                u(reg, "facility_count", "Sum"),
                ", of which buildings: ",
                u(reg, "building_count", "Sum"),
                "\nSubstations ≥ 230 kV: ",
                u(reg, "bulk_substation_count", "Sum"),
            ),
        ),
        Sheet(
            name="Load vs grid",
            title="Inferred load against bulk transmission, by state",
            ds=reg,
            mark="Circle",
            rows=(u(reg, "Estimated MW", "Sum"),),
            cols=(u(reg, "bulk_substation_count", "Sum"),),
            detail=(u(reg, "name"),),
            label=(u(reg, "state"),),
            show_labels=True,
            filters=(state_rows, has_mw),
            tooltip=(
                u(reg, "name"),
                "\nEstimated MW (inferred): ",
                u(reg, "Estimated MW", "Sum"),
                "\nSubstations ≥ 230 kV: ",
                u(reg, "bulk_substation_count", "Sum"),
                "   all ≥ 69 kV: ",
                u(reg, "substation_count", "Sum"),
                "\nHighest voltage: ",
                u(reg, "Max voltage kV", "Sum"),
                " kV\nPlant capacity where tagged: ",
                u(reg, "Tagged plant capacity MW", "Sum"),
                " MW\nPlants with no capacity tag: ",
                u(reg, "plants_without_capacity", "Sum"),
            ),
        ),
        Sheet(
            name="Mapped over time",
            title="Data centres on the map, month by month",
            ds=ser,
            mark="Line",
            rows=(u(ser, "Selected region count", "Sum"),),
            cols=(u(ser, "Month", "None", "quantitative"),),
            color=u(ser, "Era"),
            parameters=(param,),
            tooltip=(
                u(ser, "Month", "None", "quantitative"),
                ": ",
                u(ser, "Selected region count", "Sum"),
                " on the map\n",
                u(ser, "Era"),
            ),
        ),
        Sheet(
            name="Edits by year",
            title="OpenStreetMap edits to data centres, by year",
            ds=evt,
            mark="Bar",
            cols=(u(evt, "Year"),),
            rows=(u(evt, "Edits", "Sum"),),
            color=u(evt, "Edit kind"),
            tooltip=(
                u(evt, "Year"),
                ": ",
                u(evt, "Edits", "Sum"),
                " edits, ",
                u(evt, "Edit kind"),
            ),
        ),
        Sheet(
            name="National electricity",
            title="US data-centre electricity, reported and projected (LBNL)",
            ds=nrg,
            mark="Shape",
            cols=(u(nrg, "year"),),
            rows=(u(nrg, "electricity_twh", "Sum"),),
            color=u(nrg, "Series"),
            shape=u(nrg, "assertion_class"),
            text=u(nrg, "electricity_twh", "Sum"),
            show_labels=True,
            detail=(u(nrg, "source"),),
            tooltip=(
                u(nrg, "year"),
                ": ",
                u(nrg, "electricity_twh", "Sum"),
                " TWh\n",
                u(nrg, "Series"),
                " (",
                u(nrg, "assertion_class"),
                ")\nSource: ",
                u(nrg, "source"),
            ),
        ),
        Sheet(
            name="Construction map",
            title="Records mapped as under construction",
            ds=fac,
            mark="Circle",
            rows=(u(fac, "lat", "Avg"),),
            cols=(u(fac, "lon", "Avg"),),
            color=u(fac, "site_class"),
            detail=(u(fac, "osm_type"), u(fac, "osm_id")),
            filters=(Filter(u(fac, "site_class"), ('"construction"',)),),
            tooltip=facility_tooltip,
        ),
        Sheet(
            name="Construction list",
            title="Under construction: mapped land, not capacity",
            ds=fac,
            mark="Text",
            rows=(u(fac, "state"), u(fac, "Facility label"), u(fac, "osm_id")),
            text=u(fac, "Mapped area m2", "Sum"),
            filters=(Filter(u(fac, "site_class"), ('"construction"',)),),
            tooltip=(
                u(fac, "Facility label"),
                "\nOperator: ",
                u(fac, "Operator label"),
                "\nMapped land: ",
                u(fac, "Mapped area m2", "Sum"),
                " m²\nFirst seen in OpenStreetMap: ",
                u(fac, "First seen label"),
            ),
        ),
    )


# ------------------------------------------------------------- XML: sources --


def _sub(parent: ET.Element, tag: str, **attrs: str) -> ET.Element:
    return ET.SubElement(parent, tag, {k: v for k, v in attrs.items() if v is not None})


def _column_element(parent: ET.Element, f: Field) -> ET.Element:
    attrs: dict[str, str] = {}
    if f.aggregation:
        attrs["aggregation"] = f.aggregation
    attrs["caption"] = f.caption
    attrs["datatype"] = f.datatype
    if f.default_format:
        attrs["default-format"] = f.default_format
    attrs["name"] = f.ref
    attrs["role"] = f.role
    if f.semantic_role:
        attrs["semantic-role"] = f.semantic_role
    attrs["type"] = f.type
    col = ET.SubElement(parent, "column", attrs)
    if f.formula is not None:
        _sub(col, "calculation", **{"class": "tableau", "formula": f.formula})
    if f.aliases:
        aliases = _sub(col, "aliases")
        for key, value in f.aliases:
            _sub(aliases, "alias", key=f'"{key}"', value=value)
    return col


def build_datasource(parent: ET.Element, ds: DataSource) -> None:
    el = _sub(parent, "datasource", caption=ds.caption, inline="true", name=ds.name, version="18.1")
    conn = _sub(el, "connection", **{"class": "federated"})
    named = _sub(_sub(conn, "named-connections"), "named-connection")
    named.set("name", ds.connection)
    # Attribute for attribute, the connection Tableau Public's bundled
    # "World Indicators" data source makes to its own .hyper file.
    _sub(
        named,
        "connection",
        **{
            "authentication": "auth-none",
            "author-locale": "en_US",
            "class": "hyper",
            "dbname": f"{PACKAGE_DATA_DIR}/{ds.name}.hyper",
            "default-settings": "yes",
            "sslmode": "",
            "username": "tableau_internal_user",
        },
    )
    _sub(
        conn,
        "relation",
        connection=ds.connection,
        name="Extract",
        table="[Extract].[Extract]",
        type="table",
    )
    _sub(el, "aliases", enabled="yes")
    for f in sorted(ds.fields().values(), key=lambda f: f.name):
        _column_element(el, f)
    if ds.palettes:
        rule = _sub(_sub(el, "style"), "style-rule", element="mark")
        for field_name, mapping in ds.palettes:
            ftype = ds.fields()[field_name].type
            enc = _sub(
                rule,
                "encoding",
                attr="color",
                field=f"[none:{field_name}:{TYPE_SUFFIX[ftype]}]",
                type="palette",
            )
            for value, colour in mapping:
                _sub(_sub(enc, "map", to=colour), "bucket").text = f'"{value}"'
    sv = _sub(el, "semantic-values")
    _sub(sv, "semantic-value", key="[Country].[Name]", value='"United States"')


def build_parameters(parent: ET.Element, param: Parameter) -> None:
    el = _sub(parent, "datasource", hasconnection="false", inline="true", name="Parameters")
    el.set("version", "18.1")
    _sub(el, "aliases", enabled="yes")
    _parameter_column(el, param)


def _parameter_column(parent: ET.Element, param: Parameter) -> ET.Element:
    col = _sub(
        parent,
        "column",
        caption=param.caption,
        datatype="string",
        name=param.ref,
        role="measure",
        type="nominal",
        value=f'"{param.default}"',
    )
    col.set("param-domain-type", "list")
    _sub(col, "calculation", **{"class": "tableau", "formula": f'"{param.default}"'})
    members = _sub(col, "members")
    for value, alias in param.members:
        _sub(members, "member", alias=alias, value=f'"{value}"')
    return col


# -------------------------------------------------------------- XML: sheets --

_FIELD_REF = re.compile(r"\[([^\[\]]+)\]")


def _dependencies(ds: DataSource, names: set[str]) -> list[Field]:
    """Every field the named ones need, following formulas transitively."""
    fields = ds.fields()
    seen: set[str] = set()
    stack = list(names)
    while stack:
        name = stack.pop()
        if name in seen or name not in fields:
            continue
        seen.add(name)
        formula = fields[name].formula or ""
        # Drop "[Parameters].[...]" before scanning: it is not this source's.
        stack.extend(_FIELD_REF.findall(re.sub(r"\[Parameters\]\.\[[^\]]+\]", "", formula)))
    return [fields[n] for n in sorted(seen)]


def _sheet_uses(sheet: Sheet) -> list[Use]:
    uses: list[Use] = [*sheet.rows, *sheet.cols, *sheet.detail]
    for enc in (sheet.color, sheet.shape, sheet.text):
        if enc:
            uses.append(enc)
    uses.extend(p for p in (*sheet.tooltip, *sheet.label) if isinstance(p, Use))
    uses.extend(f.use for f in sheet.filters)
    if sheet.sort:
        uses.extend(sheet.sort[:2])
    return uses


def _formatted(parent: ET.Element, parts: tuple[str | Use, ...], *, bold: bool = False) -> None:
    text = _sub(parent, "formatted-text")
    for part in parts:
        run = _sub(text, "run")
        if isinstance(part, Use):
            run.set("bold", "true")
            run.text = f"<{part.qualified}>"
        else:
            if bold:
                run.set("bold", "true")
            run.text = part


def _title(parent: ET.Element, title: str) -> None:
    layout = _sub(parent, "layout-options")
    _formatted(_sub(layout, "title"), (title,), bold=True)


def build_worksheet(parent: ET.Element, sheet: Sheet) -> None:
    ws = _sub(parent, "worksheet", name=sheet.name)
    _title(ws, sheet.title)
    table = _sub(ws, "table")
    view = _sub(table, "view")
    sources = _sub(view, "datasources")
    if sheet.parameters:
        _sub(sources, "datasource", name="Parameters")
    _sub(sources, "datasource", caption=sheet.ds.caption, name=sheet.ds.name)
    if sheet.parameters:
        pdeps = _sub(view, "datasource-dependencies", datasource="Parameters")
        for param in sheet.parameters:
            _parameter_column(pdeps, param)

    uses = _sheet_uses(sheet)
    deps = _sub(view, "datasource-dependencies", datasource=sheet.ds.name)
    for f in _dependencies(sheet.ds, {x.field for x in uses}):
        _column_element(deps, f)
    instances = {x.instance: x for x in uses}
    for name in sorted(instances):
        x = instances[name]
        _sub(
            deps,
            "column-instance",
            column=f"[{x.field}]",
            derivation=x.derivation,
            name=x.instance,
            pivot="key",
            type=x.instance_type,
        )

    for flt in sheet.filters:
        el = _sub(view, "filter", **{"class": "categorical", "column": flt.use.qualified})
        members = [
            {
                "function": "member",
                "level": flt.use.instance,
                "member": m,
            }
            for m in flt.members
        ]
        target = el
        if len(members) > 1:
            target = _sub(el, "groupfilter", function="union")
        for m in members:
            gf = _sub(target, "groupfilter", **m)
            gf.set(_attr("ui-domain"), "database")
            gf.set(_attr("ui-enumeration"), "inclusive")
            gf.set(_attr("ui-marker"), "enumerate")
    if sheet.sort:
        dim, by, direction = sheet.sort
        _sub(
            view,
            "sort",
            **{
                "class": "computed",
                "column": dim.qualified,
                "direction": direction,
                "using": by.qualified,
            },
        )
    if sheet.filters:
        slices = _sub(view, "slices")
        for flt in sheet.filters:
            _sub(slices, "column").text = flt.use.qualified
    _sub(view, "aggregation", value="true")

    _sub(table, "style")
    panes = _sub(table, "panes")
    pane = _sub(panes, "pane", id="0")
    _sub(_sub(pane, "view"), "breakdown", value="auto")
    _sub(pane, "mark", **{"class": sheet.mark})
    encodings = _sub(pane, "encodings")
    if sheet.color:
        _sub(encodings, "color", column=sheet.color.qualified)
    if sheet.shape:
        _sub(encodings, "shape", column=sheet.shape.qualified)
    if sheet.text:
        _sub(encodings, "text", column=sheet.text.qualified)
    on_shelf = {x.qualified for x in (*sheet.rows, *sheet.cols)}
    on_shelf |= {e.qualified for e in (sheet.color, sheet.shape, sheet.text) if e}
    placed: set[str] = set()
    for part in sheet.label:
        if isinstance(part, Use) and part.qualified not in on_shelf | placed:
            _sub(encodings, "text", column=part.qualified)
            placed.add(part.qualified)
    for part in sheet.tooltip:
        if isinstance(part, Use) and part.qualified not in on_shelf | placed:
            _sub(encodings, "tooltip", column=part.qualified)
            placed.add(part.qualified)
    for d in sheet.detail:
        if d.qualified not in on_shelf | placed:
            _sub(encodings, "lod", column=d.qualified)
            placed.add(d.qualified)
    if sheet.tooltip:
        _formatted(_sub(pane, "customized-tooltip"), sheet.tooltip)
    if sheet.label:
        _formatted(_sub(pane, "customized-label"), sheet.label)
    if sheet.show_labels:
        rule = _sub(_sub(pane, "style"), "style-rule", element="mark")
        _sub(rule, "format", attr="mark-labels-show", value="true")
        _sub(rule, "format", attr="mark-labels-cull", value="true")

    _sub(table, "rows").text = _nest(sheet.rows) if sheet.rows else None
    _sub(table, "cols").text = _nest(sheet.cols) if sheet.cols else None


def _nest(uses: tuple[Use, ...]) -> str:
    """Tableau's shelf syntax nests left to right: (a / (b / c))."""
    names = [x.qualified for x in uses]
    out = names[-1]
    for name in reversed(names[:-1]):
        out = f"({name} / {out})"
    return out


# ---------------------------------------------------------- XML: dashboards --


@dataclass
class Zone:
    kind: str  # sheet | text | color | paramctrl | vert | horz | blank
    weight: float = 1.0
    sheet: str | None = None
    param: str | None = None
    text: tuple[tuple[str, dict[str, str]], ...] = ()
    children: list[Zone] = field(default_factory=list)
    show_title: bool = True


def sheet_zone(name: str, weight: float = 1.0, *, show_title: bool = True) -> Zone:
    return Zone("sheet", weight, sheet=name, show_title=show_title)


def text_zone(weight: float, *runs: tuple[str, dict[str, str]]) -> Zone:
    return Zone("text", weight, text=runs)


def vert(weight: float, *children: Zone) -> Zone:
    return Zone("vert", weight, children=list(children))


def horz(weight: float, *children: Zone) -> Zone:
    return Zone("horz", weight, children=list(children))


HEADING = {"bold": "true", "fontsize": "18", "fontcolor": INK}
SUBHEAD = {"fontsize": "11", "fontcolor": "#4e4f45"}
BODY = {"fontsize": "10", "fontcolor": "#4e4f45"}


@dataclass(frozen=True)
class Dashboard:
    name: str
    root: Zone


def _split(total: int, weights: list[float]) -> list[int]:
    """Divide an integer extent by weight, with no unit lost to rounding."""
    whole = sum(weights)
    edges = [round(total * sum(weights[: i + 1]) / whole) for i in range(len(weights))]
    return [b - a for a, b in zip([0, *edges[:-1]], edges, strict=True)]


def _place(parent: ET.Element, zone: Zone, box: tuple[int, int, int, int], ids: list[int]) -> None:
    x, y, w, h = box
    ids[0] += 1
    attrs = {"h": str(h), "id": str(ids[0]), "w": str(w), "x": str(x), "y": str(y)}
    if zone.kind in ("vert", "horz"):
        el = _sub(parent, "zone", param=zone.kind, **attrs)
        el.set("type", "layout-flow")
        sizes = _split(h if zone.kind == "vert" else w, [c.weight for c in zone.children])
        offset = 0
        for child, size in zip(zone.children, sizes, strict=True):
            if zone.kind == "vert":
                _place(el, child, (x, y + offset, w, size), ids)
            else:
                _place(el, child, (x + offset, y, size, h), ids)
            offset += size
        return
    if zone.kind == "sheet":
        el = _sub(parent, "zone", name=zone.sheet, **attrs)
        el.set("show-title", "true" if zone.show_title else "false")
    elif zone.kind == "text":
        el = _sub(parent, "zone", **attrs)
        el.set("type", "text")
        text = _sub(el, "formatted-text")
        for content, style in zone.text:
            _sub(text, "run", **style).text = content
    elif zone.kind == "color":
        el = _sub(parent, "zone", name=zone.sheet, param=zone.param, **attrs)
        el.set("pane-specification-id", "0")
        el.set("type", "color")
    elif zone.kind == "paramctrl":
        el = _sub(parent, "zone", param=zone.param, **attrs)
        el.set("mode", "compact")
        el.set("type", "paramctrl")
    else:
        el = _sub(parent, "zone", **attrs)
        el.set("type", "empty")


def build_dashboard(parent: ET.Element, dash: Dashboard, param: Parameter) -> None:
    el = _sub(parent, "dashboard", name=dash.name)
    _sub(el, "style")
    size = str(DASHBOARD_WIDTH), str(DASHBOARD_HEIGHT)
    _sub(
        el,
        "size",
        maxheight=size[1],
        maxwidth=size[0],
        minheight=size[1],
        minwidth=size[0],
    )
    if any(z.kind == "paramctrl" for z in _walk(dash.root)):
        sources = _sub(el, "datasources")
        _sub(sources, "datasource", name="Parameters")
        deps = _sub(el, "datasource-dependencies", datasource="Parameters")
        _parameter_column(deps, param)
    zones = _sub(el, "zones")
    root = _sub(zones, "zone", h="100000", id="1", type="layout-basic", w="100000", x="0", y="0")
    _place(root, dash.root, (0, 0, 100000, 100000), [1])


def _walk(zone: Zone) -> list[Zone]:
    out = [zone]
    for child in zone.children:
        out.extend(_walk(child))
    return out


def build_dashboards(facts: dict[str, str], param: Parameter) -> tuple[Dashboard, ...]:
    site_legend = Zone("color", 1, sheet="Facility map", param="[facilities].[none:site_class:nk]")
    return (
        Dashboard(
            "Where they are",
            vert(
                1,
                text_zone(
                    0.09,
                    ("US data centres, as OpenStreetMap records them\n", HEADING),
                    (
                        f"{facts['facilities']} facilities in {facts['counties']} counties. "
                        f"Snapshot polled {facts['polled']}. A count of what has been "
                        "mapped, not a census: completeness cannot be measured.",
                        SUBHEAD,
                    ),
                ),
                horz(
                    0.13,
                    sheet_zone("KPI facilities", show_title=False),
                    sheet_zone("KPI buildings", show_title=False),
                    sheet_zone("KPI construction", show_title=False),
                    sheet_zone("KPI counties", show_title=False),
                ),
                horz(
                    0.66,
                    sheet_zone("Facility map", 0.66),
                    vert(0.34, site_legend, sheet_zone("Facilities by state", 4)),
                ),
                text_zone(
                    0.12,
                    (
                        "Only buildings carry a floor area. A campus mapped as land and a "
                        "site mapped as under construction keep their land area and get no "
                        "power figure; a point has no geometry at all. Hover a facility for "
                        "what its area measures. Source: OpenStreetMap contributors (ODbL), "
                        "via the Overpass API.",
                        BODY,
                    ),
                ),
            ),
        ),
        Dashboard(
            "Power and grid",
            vert(
                1,
                text_zone(
                    0.1,
                    ("Where the measured national load lands, by floor area\n", HEADING),
                    (
                        f"Inferred. LBNL reports {facts['twh']} TWh for {facts['year']} "
                        f"({facts['mw']} MW average). That total is split across mapped "
                        "buildings by floor-area share, so each figure is an upper bound, "
                        "not a meter reading. Regions with no mapped building get no "
                        "estimate rather than 0 MW and are left off these charts.",
                        SUBHEAD,
                    ),
                ),
                horz(
                    0.56,
                    sheet_zone("State allocation"),
                    sheet_zone("County allocation"),
                ),
                horz(
                    0.34,
                    sheet_zone("Load vs grid", 0.64),
                    text_zone(
                        0.36,
                        ("Reading the grid chart\n", {"bold": "true", "fontsize": "11"}),
                        (
                            "Substations are counted, not sized: transformer capacity is "
                            "not public (FERC Form 715 is CEII-restricted). A plant with "
                            "no capacity tag is counted apart rather than summed as zero, "
                            "and a state whose plants are all untagged shows no capacity. "
                            "Grid assets in Mexico and Canada are excluded by county "
                            "assignment.",
                            BODY,
                        ),
                    ),
                ),
            ),
        ),
        Dashboard(
            "Through time",
            vert(
                1,
                text_zone(
                    0.1,
                    ("When the map recorded them, not when they were built\n", HEADING),
                    (
                        "OpenStreetMap carries no build dates. These are mapping dates. "
                        "Before 2017 the data-centre tag was still being adopted, so the "
                        "early curve measures the tag, not the country. A removal means "
                        "removed from OpenStreetMap, never demolished.",
                        SUBHEAD,
                    ),
                ),
                horz(
                    0.46,
                    sheet_zone("Mapped over time", 0.76),
                    vert(
                        0.24,
                        Zone("paramctrl", 1, param=f"[Parameters].{param.ref}"),
                        Zone(
                            "color",
                            2,
                            sheet="Mapped over time",
                            param="[region_series].[none:Era:nk]",
                        ),
                        Zone("blank", 3),
                    ),
                ),
                horz(
                    0.44,
                    sheet_zone("Edits by year"),
                    sheet_zone("National electricity"),
                ),
            ),
        ),
        Dashboard(
            "Under construction",
            vert(
                1,
                text_zone(
                    0.1,
                    ("Where capacity is being built\n", HEADING),
                    (
                        f"{facts['construction']} records are mapped as under "
                        "construction. Their area is land being built on, so no MW is "
                        "assigned, and their first appearance in OpenStreetMap is not a "
                        "construction start date.",
                        SUBHEAD,
                    ),
                ),
                horz(
                    0.9,
                    sheet_zone("Construction map", 0.55),
                    sheet_zone("Construction list", 0.45),
                ),
            ),
        ),
        Dashboard(
            "About the data",
            vert(
                1,
                text_zone(
                    1,
                    ("About this workbook\n\n", HEADING),
                    (
                        "Every figure here carries one of these claims, and the "
                        "workbook keeps them apart.\n\n",
                        SUBHEAD,
                    ),
                    ("Reported. ", {"bold": "true", "fontsize": "11"}),
                    (
                        "Stated by an authoritative party: a facility tagged in "
                        "OpenStreetMap; LBNL's national electricity totals.\n",
                        BODY,
                    ),
                    ("Inferred. ", {"bold": "true", "fontsize": "11"}),
                    (
                        "Concluded from indirect signals: every MW and water figure for a "
                        "county or state is a floor-area share of the national total.\n",
                        BODY,
                    ),
                    ("Predicted. ", {"bold": "true", "fontsize": "11"}),
                    ("LBNL's scenario projections for 2028 and 2030.\n", BODY),
                    ("Unknown. ", {"bold": "true", "fontsize": "11"}),
                    (
                        "Not established, and shown as absent, never as zero.\n\n",
                        BODY,
                    ),
                    ("Never asserted\n", {"bold": "true", "fontsize": "11"}),
                    (
                        "When a facility was built, and that a removal from the map means "
                        "a demolition. Neither is in any public source this workbook "
                        "reads.\n\n",
                        BODY,
                    ),
                    ("Sources\n", {"bold": "true", "fontsize": "11"}),
                    (
                        "OpenStreetMap contributors (ODbL) via Overpass and the ohsome API "
                        "(HeiGIT); US Census Bureau TIGERweb county boundaries; Lawrence "
                        "Berkeley National Laboratory, United States Data Center Energy "
                        "Usage Report (2024) and 2025 Update.\n\n",
                        BODY,
                    ),
                    (
                        "Built from the committed CSVs by "
                        "scripts/observatory/build_tableau_workbook.py. Live site: "
                        "https://us-data-center-observatory.varadmore.me/",
                        BODY,
                    ),
                ),
            ),
        ),
    )


# -------------------------------------------------------------- XML: windows --


def build_windows(
    parent: ET.Element, dashboards: tuple[Dashboard, ...], sheets: tuple[Sheet, ...]
) -> None:
    windows = _sub(parent, "windows", **{"source-height": "30"})
    for dash in dashboards:
        win = _sub(
            windows, "window", **{"class": "dashboard", "maximized": "true", "name": dash.name}
        )
        points = _sub(win, "viewpoints")
        for z in sorted({z.sheet for z in _walk(dash.root) if z.kind == "sheet"}):
            _sub(points, "viewpoint", name=z)
        _sub(win, "active", id="-1")
    for sheet in sheets:
        win = _sub(
            windows,
            "window",
            **{"class": "worksheet", "hidden": "true", "maximized": "true", "name": sheet.name},
        )
        cards = _sub(win, "cards")
        left = _sub(_sub(cards, "edge", name="left"), "strip", size="160")
        for card in ("pages", "filters", "marks"):
            _sub(left, "card", type=card)
        top = _sub(cards, "edge", name="top")
        for card in ("columns", "rows", "title"):
            _sub(_sub(top, "strip", size="2147483647"), "card", type=card)


# --------------------------------------------------------------- assembling --


def _facts(data_dir: Path) -> dict[str, str]:
    """The handful of numbers the dashboard text quotes, read from the data so
    the prose cannot drift from the charts beside it."""
    facilities = read_csv(data_dir / "facilities.csv")
    energy = [
        r for r in read_csv(data_dir / "national_energy.csv") if r["series_kind"] == "historical"
    ]
    latest = max(energy, key=lambda r: int(r["year"]))
    twh = float(latest["electricity_twh"])
    polls = read_csv(data_dir / "poll_log.csv")
    return {
        "facilities": f"{len(facilities):,}",
        "counties": f"{len({r['county_fips'] for r in facilities if r['county_fips']}):,}",
        "construction": f"{sum(1 for r in facilities if r['site_class'] == 'construction'):,}",
        "polled": polls[-1]["polled_at"] if polls else "unknown",
        "twh": f"{twh:,.0f}",
        "year": latest["year"],
        # Same conversion allocate_power.py uses: annual energy over 8,760 hours.
        "mw": f"{twh * 1_000_000 / 8760:,.0f}",
    }


def build_workbook(data_dir: Path = DATA_DIR) -> ET.ElementTree:
    """Return the workbook XML for the CSVs in ``data_dir``."""
    param = build_parameter(read_csv(data_dir / "region_series.csv"))
    sheets = build_sheets(param)
    dashboards = build_dashboards(_facts(data_dir), param)

    wb = ET.Element(
        "workbook",
        {
            "locale": "en_US",
            "source-build": "0.0.0 (0000.0.0.0)",
            "source-platform": "mac",
            "version": WORKBOOK_VERSION,
        },
    )
    _sub(_sub(wb, "preferences"), "preference", name="ui.encoding.shelf.height", value="24")
    sources = _sub(wb, "datasources")
    build_parameters(sources, param)
    for ds in DATASOURCES:
        build_datasource(sources, ds)
    _sub(_sub(wb, "mapsources"), "mapsource", name="Tableau")
    worksheets = _sub(wb, "worksheets")
    for sheet in sheets:
        build_worksheet(worksheets, sheet)
    dash_el = _sub(wb, "dashboards")
    for dash in dashboards:
        build_dashboard(dash_el, dash, param)
    build_windows(wb, dashboards, sheets)
    ET.indent(wb, space="  ")
    return ET.ElementTree(wb)


def workbook_bytes(tree: ET.ElementTree) -> bytes:
    body = ET.tostring(tree.getroot(), encoding="unicode")
    return ("<?xml version='1.0' encoding='utf-8' ?>\n\n" + body + "\n").encode("utf-8")


def _typed(value: str, datatype: str) -> object:
    """A CSV cell as the extract stores it. An empty cell is unknown, so it is
    stored as null, never as 0 or an empty string."""
    if value == "":
        return None
    if datatype == "integer":
        return int(value)
    if datatype == "real":
        return float(value)
    if datatype == "date":
        return date.fromisoformat(value)
    return value


def extract_rows(ds: DataSource, data_dir: Path = DATA_DIR) -> list[tuple[object, ...]]:
    """The rows of one extract, in the order of the first table's CSV.

    A left join: a row of the first table with no match in a joined table keeps
    its row, with nulls for the joined columns.
    """
    first, *joined = ds.tables
    lookups = []
    for table in joined:
        assert ds.join_key is not None
        lookups.append({r[ds.join_key]: r for r in read_csv(data_dir / table.filename)})
    rows = []
    for row in read_csv(data_dir / first.filename):
        values = [_typed(row[c.name], c.datatype) for c in first.columns]
        for table, lookup in zip(joined, lookups, strict=True):
            match = lookup.get(row[ds.join_key]) if ds.join_key else None
            values.extend(
                _typed(match[c.name], c.datatype) if match else None for c in table.columns
            )
        rows.append(tuple(values))
    return rows


def write_extracts(out_dir: Path, data_dir: Path = DATA_DIR) -> list[Path]:
    """Write one ``<datasource>.hyper`` per data source into ``out_dir``."""
    # Imported here so the rest of the module, and its tests, run without it.
    from tableauhyperapi import (
        Connection,
        CreateMode,
        HyperProcess,
        Inserter,
        Nullability,
        SqlType,
        TableDefinition,
        TableName,
        Telemetry,
    )

    types = {
        "string": SqlType.text(),
        "integer": SqlType.big_int(),
        "real": SqlType.double(),
        "date": SqlType.date(),
    }
    paths = []
    # log_config "" keeps hyperd from writing a log file into the working tree.
    with HyperProcess(
        telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU, parameters={"log_config": ""}
    ) as hyper:
        for ds in DATASOURCES:
            path = out_dir / f"{ds.name}.hyper"
            table = TableDefinition(
                TableName("Extract", "Extract"),
                [
                    TableDefinition.Column(c.name, types[c.datatype], Nullability.NULLABLE)
                    for c in ds.columns()
                ],
            )
            with Connection(hyper.endpoint, path, CreateMode.CREATE_AND_REPLACE) as conn:
                conn.catalog.create_schema("Extract")
                conn.catalog.create_table(table)
                with Inserter(conn, table) as inserter:
                    inserter.add_rows(extract_rows(ds, data_dir))
                    inserter.execute()
            paths.append(path)
    return paths


def write_twbx(out: Path = OUT_PATH, data_dir: Path = DATA_DIR) -> Path:
    """Write the packaged workbook: the .twb, then each extract."""
    out.parent.mkdir(parents=True, exist_ok=True)
    entries: list[tuple[str, bytes]] = [(TWB_NAME, workbook_bytes(build_workbook(data_dir)))]
    with tempfile.TemporaryDirectory() as scratch:
        for path in write_extracts(Path(scratch), data_dir):
            entries.append((f"{PACKAGE_DATA_DIR}/{path.name}", path.read_bytes()))
    tmp = out.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in entries:
            info = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, payload)
    tmp.replace(out)
    return out


def check_headers(data_dir: Path = DATA_DIR) -> list[str]:
    """Columns the workbook reads that a CSV no longer has.

    A missing column would otherwise surface as a KeyError halfway through an
    extract, or as a broken field in Tableau, so a pipeline change that renames
    one has to fail here, by name.
    """
    problems = []
    for ds in DATASOURCES:
        for table in ds.tables:
            with (data_dir / table.filename).open(newline="", encoding="utf-8") as fh:
                header = next(csv.reader(fh))
            needed = [c.name for c in table.columns] + ([ds.join_key] if ds.join_key else [])
            missing = [n for n in needed if n not in header]
            if missing:
                problems.append(f"{table.filename}: no column {', '.join(missing)}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--twb", type=Path, help="Also write the bare .twb here, for inspection")
    args = parser.parse_args(argv)

    problems = check_headers()
    if problems:
        for p in problems:
            print(f"!! {p}", file=sys.stderr)
        return 1
    path = write_twbx(args.out)
    if args.twb:
        args.twb.write_bytes(workbook_bytes(build_workbook()))
    print(f"Wrote {path} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
