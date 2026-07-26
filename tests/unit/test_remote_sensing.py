"""Unit tests for remote sensing change detection logic."""

import pytest

from helios_remote_sensing.change_detector import analyze_change

pytestmark = pytest.mark.unit


def test_analyze_change_significant_disturbance():
    """Test a clear case of earth disturbance (e.g., bare earth up, vegetation down)."""
    result = analyze_change(ndsi_change=0.45, ndvi_change=-0.35, cloud_cover=5.0)
    assert result.is_significant is True
    assert result.confidence > 0.7


def test_analyze_change_no_disturbance():
    """Test when metrics don't breach thresholds."""
    result = analyze_change(ndsi_change=0.1, ndvi_change=-0.1, cloud_cover=5.0)
    assert result.is_significant is False
    assert result.confidence < 0.3


def test_analyze_change_cloud_penalty():
    """Test that cloud cover obscures otherwise strong signals."""
    result = analyze_change(ndsi_change=0.5, ndvi_change=-0.5, cloud_cover=85.0)
    assert result.is_significant is False
    assert result.confidence == 0.1
    assert "Obscured by cloud cover" in result.description
