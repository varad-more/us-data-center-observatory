"""Tests for impact estimation models."""

import pytest

from helios_scoring.impact import (
    GAL_PER_KWH_LIKELY,
    MW_PER_ACRE_LIKELY,
    estimate_power_mw,
    estimate_water_gpd,
)

pytestmark = pytest.mark.unit


def test_estimate_power_mw_likely_tracks_the_baseline_density():
    assert estimate_power_mw(10.0, 0).likely == 20.0
    assert estimate_power_mw(100.0, 5).likely == 200.0


def test_estimate_power_mw_applies_a_stage_density_multiplier():
    assert estimate_power_mw(10.0, 6).likely == 24.0
    assert estimate_power_mw(10.0, 7).likely == 24.0
    assert estimate_power_mw(10.0, 8).likely == 30.0


def test_estimate_power_mw_without_acreage_is_none():
    assert estimate_power_mw(None, 4) is None
    assert estimate_power_mw(0.0, 4) is None


def test_estimate_water_gpd_likely_tracks_the_baseline_intensity():
    power = estimate_power_mw(10.0, 0)  # 20 MW likely
    water = estimate_water_gpd(power)
    # 20 MW * 1000 kW * 24 h * 0.5 gal/kWh
    assert water.likely == 240000.0


def test_estimate_water_gpd_without_power_is_none():
    assert estimate_water_gpd(None) is None


def test_estimates_are_ranges_not_points():
    """The model exists to carry uncertainty; a collapsed range hides it."""
    power = estimate_power_mw(50.0, 4)
    assert power.lower < power.likely < power.upper

    water = estimate_water_gpd(power)
    assert water.lower < water.likely < water.upper


def test_water_bounds_compound_the_power_bounds():
    """The low end must pair low power with efficient cooling, and vice versa.

    Pairing the *likely* power figure with the extreme cooling coefficients would
    produce a narrower band than is warranted, understating how little is known.
    """
    power = estimate_power_mw(10.0, 0)
    water = estimate_water_gpd(power)

    # Anything narrower than power-low x cooling-low would be overconfident.
    assert water.lower <= power.lower * 1000 * 24 * GAL_PER_KWH_LIKELY
    assert water.upper >= power.upper * 1000 * 24 * GAL_PER_KWH_LIKELY


def test_estimates_carry_their_assumptions():
    """An estimate that does not state its coefficients cannot be argued with."""
    power = estimate_power_mw(10.0, 4)

    assert power.assumptions["mw_per_acre_likely"] == MW_PER_ACRE_LIKELY
    assert power.assumptions["total_acres"] == 10.0
    assert power.assumptions["stage"] == 4
    assert "note" in power.assumptions

    water = estimate_water_gpd(power)
    assert water.assumptions["gal_per_kwh_likely"] == GAL_PER_KWH_LIKELY
    assert "note" in water.assumptions


def test_method_is_stated_and_units_are_explicit():
    power = estimate_power_mw(10.0, 4)
    assert power.unit == "MW"
    assert power.method

    water = estimate_water_gpd(power)
    assert water.unit == "GPD"
    assert water.method
