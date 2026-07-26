"""Tests for impact estimation models."""

import pytest
from helios_scoring.impact import estimate_power_mw, estimate_water_gpd

pytestmark = pytest.mark.unit

def test_estimate_power_mw():
    # Base heuristic: 2 MW/acre
    assert estimate_power_mw(10.0, 0) == 20.0
    assert estimate_power_mw(100.0, 5) == 200.0
    
    # Multiplier at stage 6
    assert estimate_power_mw(10.0, 6) == 24.0
    assert estimate_power_mw(10.0, 7) == 24.0
    
    # Multiplier at stage 8
    assert estimate_power_mw(10.0, 8) == 30.0

    # None cases
    assert estimate_power_mw(None, 4) is None
    assert estimate_power_mw(0.0, 4) is None

def test_estimate_water_gpd():
    # Base heuristic: 12,000 GPD / MW
    assert estimate_water_gpd(10.0) == 120000.0
    assert estimate_water_gpd(20.0) == 240000.0
    
    # None cases
    assert estimate_water_gpd(None) is None
    assert estimate_water_gpd(0.0) is None
