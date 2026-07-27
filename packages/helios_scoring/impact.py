"""Impact estimation models for power and water."""

from __future__ import annotations


def estimate_power_mw(total_acres: float | None, stage: int) -> float | None:
    """Estimate the power capacity (MW) of a site based on acreage and stage.

    A heuristic model where baseline is 2 MW / acre. This increases slightly
    at higher confidence stages (e.g. operational might pack more density).
    """
    if total_acres is None or total_acres <= 0:
        return None

    base_mw_per_acre = 2.0

    # Slight density multiplier for later stages (e.g. multi-story or higher utilization)
    multiplier = 1.0
    if stage >= 6:
        multiplier = 1.2
    if stage >= 8:
        multiplier = 1.5

    return round(float(total_acres) * base_mw_per_acre * multiplier, 1)


def estimate_water_gpd(estimated_power_mw: float | None) -> float | None:
    """Estimate water usage (Gallons Per Day) based on power.

    Uses an industry average heuristic: ~0.5 gallons per kWh for cooling.
    1 MW = 1000 kW * 24 hours = 24,000 kWh per day.
    24,000 * 0.5 = 12,000 GPD per MW.
    """
    if estimated_power_mw is None or estimated_power_mw <= 0:
        return None

    gpd_per_mw = 12000.0
    return round(estimated_power_mw * gpd_per_mw, 1)


__all__ = ["estimate_power_mw", "estimate_water_gpd"]
