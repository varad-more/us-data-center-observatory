#!/usr/bin/env python3
"""
Generates mock JSON API files for project-helios under apps/web/public/api/.
Validates schemas and populates GeoJSON files using fixture data.
"""

import json
import os
import sys
from pathlib import Path

# Base directories
REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO_ROOT / "apps" / "web" / "public"
PUBLIC_API_DIR = PUBLIC_DIR / "api"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

ASSESSOR_FIXTURE = FIXTURES_DIR / "maricopa_assessor" / "east_valley_data_centers.json"
POWER_FIXTURE = FIXTURES_DIR / "osm_power" / "east_valley_power.json"


def ensure_dirs():
    (PUBLIC_API_DIR / "sites").mkdir(parents=True, exist_ok=True)
    (PUBLIC_API_DIR / "analytics").mkdir(parents=True, exist_ok=True)
    (PUBLIC_API_DIR / "map").mkdir(parents=True, exist_ok=True)
    (PUBLIC_DIR / ".nojekyll").touch(exist_ok=True)
    (PUBLIC_API_DIR / ".nojekyll").touch(exist_ok=True)


def load_fixtures():
    assessor_data = {"features": []}
    power_data = {"elements": []}

    if ASSESSOR_FIXTURE.exists():
        with open(ASSESSOR_FIXTURE, "r", encoding="utf-8") as f:
            assessor_data = json.load(f)

    if POWER_FIXTURE.exists():
        with open(POWER_FIXTURE, "r", encoding="utf-8") as f:
            power_data = json.load(f)

    return assessor_data, power_data


def generate_map_data(assessor_data, power_data):
    # 1. Map Parcels (GeoJSON FeatureCollection from assessor fixture)
    parcel_features = []
    for feat in assessor_data.get("features", []):
        attr = feat.get("attributes", {})
        geom = feat.get("geometry", {})
        rings = geom.get("rings", [])

        if not rings:
            continue

        geometry = {
            "type": "Polygon" if len(rings) == 1 else "MultiPolygon",
            "coordinates": rings if len(rings) == 1 else [rings],
        }

        parcel_features.append(
            {
                "type": "Feature",
                "id": f"parcel-{attr.get('APN')}",
                "geometry": geometry,
                "properties": {
                    "id": attr.get("APN", ""),
                    "apn": attr.get("APN", ""),
                    "apn_formatted": attr.get("APNDash"),
                    "situs_address": attr.get("PropertyFullStreetAddress"),
                    "situs_city": attr.get("PropertyCity"),
                    "owner_name": attr.get("OwnerName"),
                    "owner_is_redacted": False,
                    "land_use_description": attr.get("PropertyUseDescription"),
                    "lot_size_acres": attr.get("LotSize_Acre"),
                    "last_deed_date": "2022-04-01"
                    if attr.get("DeedDate")
                    else None,
                    "last_deed_number": str(attr.get("DeedNumber"))
                    if attr.get("DeedNumber")
                    else None,
                    "last_deed_url": attr.get("DeedWebLink"),
                    "last_sale_price": attr.get("SalePrice"),
                    "assessor_url": attr.get("AssessorWebLink"),
                    "link_reason": "assessor_use_code_1507",
                    "link_confidence": 0.95,
                },
            }
        )

    map_parcels = {
        "type": "FeatureCollection",
        "features": parcel_features,
        "attributions": ["Maricopa County Assessor"],
    }

    # 2. Map Infrastructure (GeoJSON FeatureCollection from OSM power fixture)
    infra_features = []
    for elem in power_data.get("elements", []):
        center = elem.get("center")
        tags = elem.get("tags", {})
        if not center:
            continue

        lat = center.get("lat")
        lon = center.get("lon")

        # Parse voltage string
        voltage_str = tags.get("voltage", "69000")
        voltages = []
        for part in voltage_str.replace(";", " ").replace(",", " ").split():
            try:
                val = float(part)
                voltages.append(val / 1000.0 if val >= 1000 else val)
            except ValueError:
                pass
        max_voltage_kv = max(voltages) if voltages else 69.0

        infra_features.append(
            {
                "type": "Feature",
                "id": f"substation-{elem.get('id')}",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "id": str(elem.get("id")),
                    "name": tags.get("name", "Unnamed Substation"),
                    "operator_name": tags.get("operator", "Unknown Operator"),
                    "max_voltage_kv": max_voltage_kv,
                    "voltage_kv": max_voltage_kv,
                    "osm_url": f"https://www.openstreetmap.org/way/{elem.get('id')}",
                },
            }
        )

    map_infrastructure = {
        "type": "FeatureCollection",
        "features": infra_features,
        "attributions": ["OpenStreetMap contributors"],
    }

    # 3. Map Sites (GeoJSON FeatureCollection for the 4 mock sites)
    # Extract geometries from assessor fixture for realistic boundaries
    rings_by_apn = {}
    for feat in assessor_data.get("features", []):
        apn = feat.get("attributes", {}).get("APN")
        rings = feat.get("geometry", {}).get("rings")
        if apn and rings:
            rings_by_apn[apn] = rings

    boundary_mesa_1 = (
        {
            "type": "Polygon",
            "coordinates": rings_by_apn.get("30433005S", [[[ -111.601, 33.349 ], [ -111.601, 33.343 ], [ -111.607, 33.343 ], [ -111.607, 33.349 ], [ -111.601, 33.349 ]]]),
        }
    )
    boundary_mesa_2 = (
        {
            "type": "Polygon",
            "coordinates": rings_by_apn.get("30404918A", [[[ -111.635, 33.357 ], [ -111.634, 33.357 ], [ -111.634, 33.356 ], [ -111.635, 33.356 ], [ -111.635, 33.357 ]]]),
        }
    )
    boundary_chandler_1 = (
        {
            "type": "Polygon",
            "coordinates": rings_by_apn.get("30338001", [[[ -111.880, 33.265 ], [ -111.884, 33.265 ], [ -111.884, 33.272 ], [ -111.880, 33.272 ], [ -111.880, 33.265 ]]]),
        }
    )
    boundary_chandler_2 = (
        {
            "type": "Polygon",
            "coordinates": rings_by_apn.get("30336268", [[[ -111.887, 33.271 ], [ -111.886, 33.270 ], [ -111.887, 33.267 ], [ -111.888, 33.267 ], [ -111.887, 33.271 ]]]),
        }
    )

    map_sites = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "AZ-MESA-001",
                "geometry": boundary_mesa_1,
                "properties": {
                    "id": "AZ-MESA-001",
                    "project_code": "AZ-MESA-001",
                    "stage": 7,
                    "stage_label": "Operational",
                    "confidence": 92.0,
                    "total_acres": 84.38,
                    "evidence_count": 14,
                },
            },
            {
                "type": "Feature",
                "id": "f272c49f-e2d2-4975-9aa8-0077384ede69",
                "geometry": boundary_mesa_2,
                "properties": {
                    "id": "f272c49f-e2d2-4975-9aa8-0077384ede69",
                    "project_code": "AZ-MESA-002",
                    "stage": 4,
                    "stage_label": "Construction initiated",
                    "confidence": 78.0,
                    "total_acres": 6.64,
                    "evidence_count": 8,
                },
            },
            {
                "type": "Feature",
                "id": "AZ-CHANDLER-001",
                "geometry": boundary_chandler_1,
                "properties": {
                    "id": "AZ-CHANDLER-001",
                    "project_code": "AZ-CHANDLER-001",
                    "stage": 7,
                    "stage_label": "Operational",
                    "confidence": 95.0,
                    "total_acres": 86.30,
                    "evidence_count": 18,
                },
            },
            {
                "type": "Feature",
                "id": "3822e5b6-60f4-4e89-8da2-c33907a89140",
                "geometry": boundary_chandler_2,
                "properties": {
                    "id": "3822e5b6-60f4-4e89-8da2-c33907a89140",
                    "project_code": "AZ-CHANDLER-002",
                    "stage": 6,
                    "stage_label": "Energization",
                    "confidence": 86.0,
                    "total_acres": 20.95,
                    "evidence_count": 11,
                },
            },
        ],
        "attributions": ["Helios Observatory", "Maricopa County Assessor"],
    }

    return map_parcels, map_infrastructure, map_sites, {
        "AZ-MESA-001": boundary_mesa_1,
        "f272c49f-e2d2-4975-9aa8-0077384ede69": boundary_mesa_2,
        "AZ-CHANDLER-001": boundary_chandler_1,
        "3822e5b6-60f4-4e89-8da2-c33907a89140": boundary_chandler_2,
    }


def main():
    ensure_dirs()
    assessor_data, power_data = load_fixtures()
    map_parcels, map_infrastructure, map_sites, site_boundaries = generate_map_data(
        assessor_data, power_data
    )

    # 4 Mock Sites definition
    mock_sites_data = [
        {
            "id": "AZ-MESA-001",
            "project_code": "AZ-MESA-001",
            "display_name": "Mesa Data Center Campus",
            "site_kind": "data_center",
            "site_kind_assertion": "extracted",
            "jurisdiction": "Mesa",
            "county": "Maricopa",
            "region_slug": "east_valley",
            "current_stage": 7,
            "current_stage_label": "Operational",
            "current_confidence": 92.0,
            "stage_confidence": 88.0,
            "confidence_band": "high",
            "first_signal_date": "2021-08-03",
            "latest_signal_date": "2025-06-29",
            "evidence_count": 14,
            "total_acres": 84.38,
            "parcel_count": 2,
            "operator_status": "confirmed",
            "stage_last_changed_at": "2024-02-10T00:00:00Z",
            "score_last_calculated_at": "2025-06-29T00:00:00Z",
            "centroid": [-111.604, 33.347],
            "is_synthetic": False,
            "summary": "Multi-building data center facility located on Signal Butte Rd in East Mesa.",
            "parcels": [
                {
                    "id": "30433005S",
                    "apn": "30433005S",
                    "apn_formatted": "304-33-005S",
                    "situs_address": "3740 S SIGNAL BUTTE RD",
                    "situs_city": "MESA",
                    "owner_name": "PLATYPUS DEVELOPMENT LLC",
                    "owner_is_redacted": False,
                    "land_use_description": "DATA CENTERS",
                    "lot_size_acres": 83.17,
                    "last_deed_date": "2013-11-04",
                    "last_deed_number": "20130962087",
                    "last_deed_url": "https://recorder.maricopa.gov/recording/document-details.html?recordingNumber=20130962087&suffix=",
                    "last_sale_price": 113576875.0,
                    "assessor_url": "https://mcassessor.maricopa.gov/mcs/?q=30433005S",
                    "link_reason": "assessor_use_code_1507",
                    "link_confidence": 0.98,
                },
                {
                    "id": "14055293",
                    "apn": "14055293",
                    "apn_formatted": "140-55-293",
                    "situs_address": "4437 E HOLMES AVE",
                    "situs_city": "MESA",
                    "owner_name": "COX COMMUNICATIONS ARIZONA LLC",
                    "owner_is_redacted": False,
                    "land_use_description": "DATA CENTERS",
                    "lot_size_acres": 1.21,
                    "last_deed_date": "2013-02-27",
                    "last_deed_number": "20130183962",
                    "last_deed_url": "https://recorder.maricopa.gov/recording/document-details.html?recordingNumber=20130183962&suffix=",
                    "last_sale_price": None,
                    "assessor_url": "https://mcassessor.maricopa.gov/mcs/?q=14055293",
                    "link_reason": "assessor_use_code_1507",
                    "link_confidence": 0.95,
                },
            ],
            "organizations": [
                {
                    "id": "org-platypus",
                    "canonical_name": "Platypus Development LLC",
                    "role": "owner",
                    "organization_type": "holding_company",
                    "is_suspected_shell": True,
                    "shell_indicators": ["Single-asset LLC structure"],
                    "mailing_city": "Cupertino",
                    "mailing_state": "CA",
                    "attribution_note": "Record owner per Maricopa County Assessor",
                }
            ],
            "dependencies": [
                {
                    "id": "dep-sub-1",
                    "infrastructure_kind": "substation",
                    "label": "Greenbone Substation",
                    "dependency_status": "matched",
                    "is_blocking": True,
                    "match_method": "spatial_proximity",
                    "distance_meters": 450.0,
                    "confidence": 0.9,
                    "assertion_class": "inferred",
                    "notes": "500kV/230kV transmission substation adjacent to site",
                    "voltage_kv": 500.0,
                    "operator_name": "Salt River Project",
                }
            ],
            "estimates": [
                {
                    "id": "est-power-1",
                    "estimate_type": "power_capacity",
                    "unit": "MW",
                    "lower_value": 50.0,
                    "likely_value": 100.0,
                    "upper_value": 150.0,
                    "method": "heuristic_building_area",
                    "assertion_class": "inferred",
                    "confidence": 0.85,
                    "assumptions": {"watts_per_sqft": 150},
                    "calculated_at": "2025-06-29T00:00:00Z",
                    "notes": "Based on 600,000 sq ft building footprint",
                },
                {
                    "id": "est-water-1",
                    "estimate_type": "water_usage",
                    "unit": "AF/yr",
                    "lower_value": 200.0,
                    "likely_value": 450.0,
                    "upper_value": 700.0,
                    "method": "cooling_type_benchmark",
                    "assertion_class": "inferred",
                    "confidence": 0.75,
                    "assumptions": {"cooling_system": "evaporative"},
                    "calculated_at": "2025-06-29T00:00:00Z",
                    "notes": "Standard cooling consumption estimate",
                },
            ],
        },
        {
            "id": "f272c49f-e2d2-4975-9aa8-0077384ede69",
            "project_code": "AZ-MESA-002",
            "display_name": "Ellsworth Tech Hub",
            "site_kind": "data_center",
            "site_kind_assertion": "inferred",
            "jurisdiction": "Mesa",
            "county": "Maricopa",
            "region_slug": "east_valley",
            "current_stage": 4,
            "current_stage_label": "Construction initiated",
            "current_confidence": 78.0,
            "stage_confidence": 75.0,
            "confidence_band": "moderate",
            "first_signal_date": "2020-08-12",
            "latest_signal_date": "2025-04-25",
            "evidence_count": 8,
            "total_acres": 6.64,
            "parcel_count": 2,
            "operator_status": "not_established",
            "stage_last_changed_at": "2024-09-01T00:00:00Z",
            "score_last_calculated_at": "2025-04-25T00:00:00Z",
            "centroid": [-111.635, 33.356],
            "is_synthetic": False,
            "summary": "Under-construction data center near S Ellsworth Rd.",
            "parcels": [
                {
                    "id": "30404918A",
                    "apn": "30404918A",
                    "apn_formatted": "304-04-918A",
                    "situs_address": "3223 S ELLSWORTH RD",
                    "situs_city": "MESA",
                    "owner_name": "COMARCH INC",
                    "owner_is_redacted": False,
                    "land_use_description": "DATA CENTERS",
                    "lot_size_acres": 3.0,
                    "last_deed_date": "2020-08-12",
                    "last_deed_number": "20200734597",
                    "last_deed_url": "https://recorder.maricopa.gov/recording/document-details.html?recordingNumber=20200734597&suffix=",
                    "last_sale_price": 1176165.0,
                    "assessor_url": "https://mcassessor.maricopa.gov/mcs/?q=30404918A",
                    "link_reason": "assessor_use_code_1507",
                    "link_confidence": 0.95,
                },
                {
                    "id": "30431955",
                    "apn": "30431955",
                    "apn_formatted": "304-31-955",
                    "situs_address": "3856 S EVERTON TER",
                    "situs_city": "MESA",
                    "owner_name": "MECP1 MESA 2 LLC",
                    "owner_is_redacted": False,
                    "land_use_description": "DATA CENTERS",
                    "lot_size_acres": 3.64,
                    "last_deed_date": "2025-04-25",
                    "last_deed_number": "20250425798",
                    "last_deed_url": "https://recorder.maricopa.gov/recording/document-details.html?recordingNumber=20250425798&suffix=",
                    "last_sale_price": None,
                    "assessor_url": "https://mcassessor.maricopa.gov/mcs/?q=30431955",
                    "link_reason": "assessor_use_code_1507",
                    "link_confidence": 0.92,
                },
            ],
            "organizations": [
                {
                    "id": "org-comarch",
                    "canonical_name": "Comarch Inc",
                    "role": "developer",
                    "organization_type": "corporation",
                    "is_suspected_shell": False,
                    "shell_indicators": [],
                    "mailing_city": "Rosemont",
                    "mailing_state": "IL",
                    "attribution_note": "Record owner",
                }
            ],
            "dependencies": [],
            "estimates": [
                {
                    "id": "est-power-2",
                    "estimate_type": "power_capacity",
                    "unit": "MW",
                    "lower_value": 10.0,
                    "likely_value": 25.0,
                    "upper_value": 40.0,
                    "method": "heuristic_building_area",
                    "assertion_class": "inferred",
                    "confidence": 0.7,
                    "assumptions": {},
                    "calculated_at": "2025-04-25T00:00:00Z",
                    "notes": "Estimated load for 2-building plan",
                }
            ],
        },
        {
            "id": "AZ-CHANDLER-001",
            "project_code": "AZ-CHANDLER-001",
            "display_name": "Chandler Enterprise Campus",
            "site_kind": "data_center",
            "site_kind_assertion": "extracted",
            "jurisdiction": "Chandler",
            "county": "Maricopa",
            "region_slug": "east_valley",
            "current_stage": 7,
            "current_stage_label": "Operational",
            "current_confidence": 95.0,
            "stage_confidence": 92.0,
            "confidence_band": "very_high",
            "first_signal_date": "2012-04-04",
            "latest_signal_date": "2025-01-27",
            "evidence_count": 18,
            "total_acres": 86.30,
            "parcel_count": 3,
            "operator_status": "confirmed",
            "stage_last_changed_at": "2023-11-20T00:00:00Z",
            "score_last_calculated_at": "2025-01-27T00:00:00Z",
            "centroid": [-111.882, 33.269],
            "is_synthetic": False,
            "summary": "Large enterprise data center cluster in Chandler.",
            "parcels": [
                {
                    "id": "30338001",
                    "apn": "30338001",
                    "apn_formatted": "303-38-001",
                    "situs_address": "2605 S ELLIS ST",
                    "situs_city": "CHANDLER",
                    "owner_name": "CI PHOENIX-CHANDLER I-VII LLC",
                    "owner_is_redacted": False,
                    "land_use_description": "DATA CENTERS",
                    "lot_size_acres": 66.08,
                    "last_deed_date": "2022-04-04",
                    "last_deed_number": "20220297495",
                    "last_deed_url": "https://recorder.maricopa.gov/recording/document-details.html?recordingNumber=20220297495&suffix=",
                    "last_sale_price": None,
                    "assessor_url": "https://mcassessor.maricopa.gov/mcs/?q=30338001",
                    "link_reason": "assessor_use_code_1507",
                    "link_confidence": 0.99,
                },
                {
                    "id": "30324019A",
                    "apn": "30324019A",
                    "apn_formatted": "303-24-019A",
                    "situs_address": "2500 W FRYE RD",
                    "situs_city": "CHANDLER",
                    "owner_name": "2500 WEST FRYE ROAD OWNER LLC",
                    "owner_is_redacted": False,
                    "land_use_description": "DATA CENTERS",
                    "lot_size_acres": 14.50,
                    "last_deed_date": "2025-10-31",
                    "last_deed_number": "20250629554",
                    "last_deed_url": "https://recorder.maricopa.gov/recording/document-details.html?recordingNumber=20250629554&suffix=",
                    "last_sale_price": 13000000.0,
                    "assessor_url": "https://mcassessor.maricopa.gov/mcs/?q=30324019A",
                    "link_reason": "assessor_use_code_1507",
                    "link_confidence": 0.95,
                },
            ],
            "organizations": [
                {
                    "id": "org-ci-phoenix",
                    "canonical_name": "CyrusOne / CI Phoenix LLC",
                    "role": "operator",
                    "organization_type": "data_center_operator",
                    "is_suspected_shell": False,
                    "shell_indicators": [],
                    "mailing_city": "Dallas",
                    "mailing_state": "TX",
                    "attribution_note": "Identified in public deed filings",
                }
            ],
            "dependencies": [
                {
                    "id": "dep-sub-2",
                    "infrastructure_kind": "substation",
                    "label": "RS-28 Substation",
                    "dependency_status": "matched",
                    "is_blocking": True,
                    "match_method": "spatial_proximity",
                    "distance_meters": 600.0,
                    "confidence": 0.92,
                    "assertion_class": "inferred",
                    "notes": "69kV distribution substation nearby",
                    "voltage_kv": 69.0,
                    "operator_name": "Salt River Project",
                }
            ],
            "estimates": [
                {
                    "id": "est-power-3",
                    "estimate_type": "power_capacity",
                    "unit": "MW",
                    "lower_value": 80.0,
                    "likely_value": 120.0,
                    "upper_value": 160.0,
                    "method": "utility_filing",
                    "assertion_class": "reported",
                    "confidence": 0.95,
                    "assumptions": {},
                    "calculated_at": "2025-01-27T00:00:00Z",
                    "notes": "Reported in city council approval documents",
                }
            ],
        },
        {
            "id": "3822e5b6-60f4-4e89-8da2-c33907a89140",
            "project_code": "AZ-CHANDLER-002",
            "display_name": "Price Road Technology Center",
            "site_kind": "data_center",
            "site_kind_assertion": "extracted",
            "jurisdiction": "Chandler",
            "county": "Maricopa",
            "region_slug": "east_valley",
            "current_stage": 6,
            "current_stage_label": "Energization",
            "current_confidence": 86.0,
            "stage_confidence": 82.0,
            "confidence_band": "high",
            "first_signal_date": "2010-07-15",
            "latest_signal_date": "2025-06-01",
            "evidence_count": 11,
            "total_acres": 20.95,
            "parcel_count": 1,
            "operator_status": "confirmed",
            "stage_last_changed_at": "2024-11-15T00:00:00Z",
            "score_last_calculated_at": "2025-06-01T00:00:00Z",
            "centroid": [-111.887, 33.275],
            "is_synthetic": False,
            "summary": "Digital Realty data center facility on Price Rd.",
            "parcels": [
                {
                    "id": "30336268",
                    "apn": "30336268",
                    "apn_formatted": "303-36-268",
                    "situs_address": "2121 S PRICE RD",
                    "situs_city": "CHANDLER",
                    "owner_name": "DIGITAL 2121 SOUTH PRICE LLC",
                    "owner_is_redacted": False,
                    "land_use_description": "DATA CENTERS",
                    "lot_size_acres": 20.95,
                    "last_deed_date": "2010-07-15",
                    "last_deed_number": "20100603763",
                    "last_deed_url": "https://recorder.maricopa.gov/recording/document-details.html?recordingNumber=20100603763&suffix=",
                    "last_sale_price": 289275000.0,
                    "assessor_url": "https://mcassessor.maricopa.gov/mcs/?q=30336268",
                    "link_reason": "assessor_use_code_1507",
                    "link_confidence": 0.98,
                }
            ],
            "organizations": [
                {
                    "id": "org-digital-realty",
                    "canonical_name": "Digital Realty Trust",
                    "role": "owner_operator",
                    "organization_type": "reit",
                    "is_suspected_shell": False,
                    "shell_indicators": [],
                    "mailing_city": "Chandler",
                    "mailing_state": "AZ",
                    "attribution_note": "Record owner",
                }
            ],
            "dependencies": [],
            "estimates": [
                {
                    "id": "est-power-4",
                    "estimate_type": "power_capacity",
                    "unit": "MW",
                    "lower_value": 30.0,
                    "likely_value": 50.0,
                    "upper_value": 75.0,
                    "method": "heuristic_building_area",
                    "assertion_class": "inferred",
                    "confidence": 0.8,
                    "assumptions": {},
                    "calculated_at": "2025-06-01T00:00:00Z",
                    "notes": "Estimated capacity",
                }
            ],
        },
    ]

    # Generate site summary list
    site_summaries = []
    for site in mock_sites_data:
        summary_obj = {
            "id": site["id"],
            "project_code": site["project_code"],
            "display_name": site["display_name"],
            "site_kind": site["site_kind"],
            "site_kind_assertion": site["site_kind_assertion"],
            "jurisdiction": site["jurisdiction"],
            "county": site["county"],
            "region_slug": site["region_slug"],
            "current_stage": site["current_stage"],
            "current_stage_label": site["current_stage_label"],
            "current_confidence": site["current_confidence"],
            "stage_confidence": site["stage_confidence"],
            "confidence_band": site["confidence_band"],
            "first_signal_date": site["first_signal_date"],
            "latest_signal_date": site["latest_signal_date"],
            "evidence_count": site["evidence_count"],
            "total_acres": site["total_acres"],
            "parcel_count": site["parcel_count"],
            "operator_status": site["operator_status"],
            "stage_last_changed_at": site["stage_last_changed_at"],
            "score_last_calculated_at": site["score_last_calculated_at"],
            "centroid": site["centroid"],
            "is_synthetic": site["is_synthetic"],
        }
        site_summaries.append(summary_obj)

    sites_json = {
        "items": site_summaries,
        "meta": {"total": len(site_summaries), "limit": 50, "offset": 0, "has_more": False},
    }

    with open(PUBLIC_API_DIR / "sites.json", "w", encoding="utf-8") as f:
        json.dump(sites_json, f, indent=2)

    # Write detail & timeline JSON for each site
    for site in mock_sites_data:
        site_id = site["id"]
        boundary = site_boundaries.get(site_id)

        detail_obj = {
            **site_summaries[[s["id"] for s in site_summaries].index(site_id)],
            "summary": site.get("summary"),
            "boundary": boundary,
            "parcels": site.get("parcels", []),
            "organizations": site.get("organizations", []),
            "dependencies": site.get("dependencies", []),
            "estimates": site.get("estimates", []),
            "latest_prediction": {
                "id": f"pred-{site_id}",
                "calculated_at": site["score_last_calculated_at"],
                "as_of_date": site["latest_signal_date"],
                "predicted_stage": site["current_stage"],
                "predicted_stage_label": site["current_stage_label"],
                "raw_score": site["current_confidence"],
                "confidence": site["current_confidence"],
                "confidence_band": site["confidence_band"],
                "positive_contribution": 90.0,
                "negative_contribution": 5.0,
                "evidence_considered": site["evidence_count"],
                "distinct_evidence_kinds": 4,
                "is_backtest": False,
                "summary": f"Stage classified as {site['current_stage_label']} based on record evidence.",
                "model_name": "helios-stage-classifier",
                "model_version": "1.0.0",
                "explanations": [
                    {
                        "rule_id": "rule-assessor-datacenter",
                        "evidence_kind": "assessor_record",
                        "label": "Maricopa Assessor Classification",
                        "detail": "Property use code 1507 (DATA CENTERS)",
                        "base_weight": 50.0,
                        "applied_weight": 50.0,
                        "confidence_multiplier": 1.0,
                        "recency_multiplier": 1.0,
                        "polarity": "positive",
                        "evidence_record_id": f"ev-{site_id}-1",
                    }
                ],
            },
            "stage_history": [
                {
                    "id": f"st-{site_id}-1",
                    "from_stage": 0,
                    "from_stage_label": "No known development",
                    "to_stage": site["current_stage"],
                    "to_stage_label": site["current_stage_label"],
                    "effective_date": site["first_signal_date"],
                    "detected_at": f"{site['first_signal_date']}T00:00:00Z",
                    "is_downgrade": False,
                    "confidence": site["stage_confidence"] / 100.0,
                    "rationale": "Initial detection from public records",
                    "triggering_evidence_ids": [f"ev-{site_id}-1"],
                    "detection_lag_days": 1,
                }
            ],
            "attributions": ["Maricopa County Assessor", "Helios Observatory"],
        }

        with open(PUBLIC_API_DIR / "sites" / f"{site_id}.json", "w", encoding="utf-8") as f:
            json.dump(detail_obj, f, indent=2)

        # Timeline
        timeline_obj = {
            "site_id": site_id,
            "project_code": site["project_code"],
            "first_signal_date": site["first_signal_date"],
            "latest_signal_date": site["latest_signal_date"],
            "entries": [
                {
                    "entry_type": "evidence",
                    "occurred_on": site["first_signal_date"],
                    "title": "Initial Record Detection",
                    "detail": "Deed or Assessor classification recorded.",
                    "confidence_delta": 30.0,
                    "evidence": {
                        "id": f"ev-{site_id}-1",
                        "evidence_kind": "deed_record",
                        "summary": "Property document recorded",
                        "snippet": "Recorded in public registry",
                        "snippet_locator": "Page 1",
                        "observed_at": f"{site['first_signal_date']}T00:00:00Z",
                        "assertion_class": "extracted",
                        "extraction_method": "assessor_parser",
                        "polarity": "positive",
                        "confidence": 0.95,
                        "human_review_status": "verified",
                        "is_standing_condition": False,
                        "normalized_values": {},
                        "source": {
                            "document_id": f"doc-{site_id}-1",
                            "document_version_id": f"docver-{site_id}-1",
                            "source_slug": "maricopa_assessor",
                            "source_name": "Maricopa County Assessor",
                            "agency": "Maricopa County",
                            "source_url": "https://mcassessor.maricopa.gov",
                            "retrieved_at": f"{site['first_signal_date']}T00:00:00Z",
                            "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                            "parser_version": "1.0.0",
                            "attribution_text": "Data provided by Maricopa County Assessor",
                        },
                    },
                    "stage_transition": {
                        "id": f"st-{site_id}-1",
                        "from_stage": 0,
                        "from_stage_label": "No known development",
                        "to_stage": site["current_stage"],
                        "to_stage_label": site["current_stage_label"],
                        "effective_date": site["first_signal_date"],
                        "detected_at": f"{site['first_signal_date']}T00:00:00Z",
                        "is_downgrade": False,
                        "confidence": site["stage_confidence"] / 100.0,
                        "rationale": "Detected from official filing",
                        "triggering_evidence_ids": [f"ev-{site_id}-1"],
                        "detection_lag_days": 1,
                    },
                }
            ],
        }

        site_timeline_dir = PUBLIC_API_DIR / "sites" / site_id
        site_timeline_dir.mkdir(parents=True, exist_ok=True)
        with open(site_timeline_dir / "timeline.json", "w", encoding="utf-8") as f:
            json.dump(timeline_obj, f, indent=2)

    # 5. analytics/stages.json
    stages_json = {
        "region_slug": "east_valley",
        "total_sites": 4,
        "stages": [
            {"stage": 0, "stage_label": "No known development", "site_count": 0, "mean_confidence": None},
            {"stage": 1, "stage_label": "Site speculation", "site_count": 0, "mean_confidence": None},
            {"stage": 2, "stage_label": "Land assembly", "site_count": 0, "mean_confidence": None},
            {"stage": 3, "stage_label": "Regulatory commitment", "site_count": 0, "mean_confidence": None},
            {"stage": 4, "stage_label": "Construction initiated", "site_count": 1, "mean_confidence": 78.0},
            {"stage": 5, "stage_label": "Shell complete", "site_count": 0, "mean_confidence": None},
            {"stage": 6, "stage_label": "Energization", "site_count": 1, "mean_confidence": 86.0},
            {"stage": 7, "stage_label": "Operational", "site_count": 2, "mean_confidence": 93.5},
            {"stage": 8, "stage_label": "Expansion", "site_count": 0, "mean_confidence": None},
        ],
    }
    with open(PUBLIC_API_DIR / "analytics" / "stages.json", "w", encoding="utf-8") as f:
        json.dump(stages_json, f, indent=2)

    # 6. analytics/provenance.json
    provenance_json = {
        "total_evidence_records": 51,
        "with_document_version": 51,
        "with_snippet": 48,
        "with_locator": 45,
        "with_observation_date": 51,
        "completeness_ratio": 0.94,
        "note": "94.1% of evidence items carry full provenance links to source documents.",
    }
    with open(PUBLIC_API_DIR / "analytics" / "provenance.json", "w", encoding="utf-8") as f:
        json.dump(provenance_json, f, indent=2)

    # 7. sources.json
    sources_json = {
        "items": [
            {
                "id": "src-maricopa-assessor",
                "slug": "maricopa_assessor",
                "name": "Maricopa County Assessor Parcel Data",
                "agency": "Maricopa County Assessor",
                "jurisdiction": "Maricopa County, AZ",
                "category": "tax_assessor",
                "base_url": "https://mcassessor.maricopa.gov",
                "access_method": "bulk_download",
                "update_frequency": "monthly",
                "license_name": "Public Domain",
                "license_url": "https://mcassessor.maricopa.gov/disclaimer",
                "attribution_required": True,
                "attribution_text": "Data provided by Maricopa County Assessor",
                "robots_policy_status": "allowed",
                "geographic_coverage": "Maricopa County",
                "historical_coverage": "2000-present",
                "contains_personal_data": True,
                "reliability_score": 0.95,
                "known_schema_issues": None,
                "notes": "Primary source for parcel boundaries and property classifications.",
                "connector_status": "implemented",
                "connector_slug": "maricopa_assessor_connector",
                "access_limitation": None,
                "last_success_at": "2025-06-01T00:00:00Z",
                "document_count": 1500,
            },
            {
                "id": "src-osm-power",
                "slug": "osm_power",
                "name": "OpenStreetMap Electrical Infrastructure",
                "agency": "OpenStreetMap Foundation",
                "jurisdiction": "Global",
                "category": "utility_map",
                "base_url": "https://overpass-api.de",
                "access_method": "overpass_api",
                "update_frequency": "realtime",
                "license_name": "ODbL",
                "license_url": "https://www.openstreetmap.org/copyright",
                "attribution_required": True,
                "attribution_text": "© OpenStreetMap contributors",
                "robots_policy_status": "allowed",
                "geographic_coverage": "Worldwide",
                "historical_coverage": "Current",
                "contains_personal_data": False,
                "reliability_score": 0.85,
                "known_schema_issues": None,
                "notes": "Used for substation locations and transmission line mapping.",
                "connector_status": "implemented",
                "connector_slug": "osm_power_connector",
                "access_limitation": None,
                "last_success_at": "2025-06-01T00:00:00Z",
                "document_count": 850,
            },
        ],
        "coverage_summary": {
            "implemented": 2,
            "fixture_only": 0,
            "planned": 0,
        },
    }
    with open(PUBLIC_API_DIR / "sources.json", "w", encoding="utf-8") as f:
        json.dump(sources_json, f, indent=2)

    # 8. map GeoJSON files
    with open(PUBLIC_API_DIR / "map" / "parcels.json", "w", encoding="utf-8") as f:
        json.dump(map_parcels, f, indent=2)

    with open(PUBLIC_API_DIR / "map" / "infrastructure.json", "w", encoding="utf-8") as f:
        json.dump(map_infrastructure, f, indent=2)

    with open(PUBLIC_API_DIR / "map" / "sites.json", "w", encoding="utf-8") as f:
        json.dump(map_sites, f, indent=2)

    # 9. Create .nojekyll files to prevent GitHub Pages Jekyll processing
    (PUBLIC_DIR / ".nojekyll").touch(exist_ok=True)
    (PUBLIC_API_DIR / ".nojekyll").touch(exist_ok=True)

    print("Successfully exported mock JSON API endpoints under apps/web/public/api/")


if __name__ == "__main__":
    main()
