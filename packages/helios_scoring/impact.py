"""Impact estimation models for power and water.

These are the weakest numbers Helios publishes, and the module is shaped to keep
that visible. Each estimator returns a *range* and the coefficients it applied,
rather than a single figure that looks like a measurement.

The epistemic status is `inferred`, not `calculated`. The arithmetic is exact;
the coefficients are industry assumptions applied to a site Helios has never
visited. A value is only as strong as its weakest input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Power density of a data-centre campus, MW per acre of assembled land.
#
# The spread is genuine rather than decorative. A sprawling single-storey campus
# with large setbacks, substation yard and stormwater retention lands near the
# low end; a dense multi-storey build with high rack density lands near the top.
# Helios knows the acreage and almost never knows which of those it is looking
# at, so the band stays wide until a filing narrows it.
MW_PER_ACRE_LOW = 1.0
MW_PER_ACRE_LIKELY = 2.0
MW_PER_ACRE_HIGH = 4.0

# Cooling water, gallons per kWh.
#
# This band is enormous because the underlying practice is. Evaporative cooling
# can exceed a gallon per kWh; a closed-loop or air-cooled design approaches
# zero. Cooling type is not in any record Helios ingests, so the estimate cannot
# be narrowed and should not be presented as though it could.
GAL_PER_KWH_LOW = 0.10
GAL_PER_KWH_LIKELY = 0.50
GAL_PER_KWH_HIGH = 1.00

# Annual load factor: the fraction of nameplate capacity a campus actually draws
# averaged over a year.
#
# Needed only to put an estimated *capacity* beside a reported *consumption*,
# which are different quantities in different units. Data centres run steadier
# than almost any other large load, so the band is narrower than the others here
# -- but it is still an assumption, and it multiplies an already-inferred MW
# figure rather than replacing it.
LOAD_FACTOR_LOW = 0.60
LOAD_FACTOR_LIKELY = 0.75
LOAD_FACTOR_HIGH = 0.90

_HOURS_PER_DAY = 24
_HOURS_PER_YEAR = 8760
_KW_PER_MW = 1000


@dataclass(frozen=True)
class ImpactEstimate:
    """A ranged estimate carrying the assumptions that produced it.

    Maps onto the `SiteEstimate` columns, which were built for exactly this and
    were previously being filled with a bare `likely_value`.
    """

    lower: float
    likely: float
    upper: float
    unit: str
    method: str
    assumptions: dict[str, Any] = field(default_factory=dict)


def _stage_density_multiplier(stage: int) -> float:
    """Later stages imply a denser build than raw acreage suggests.

    A site that has energised has committed to its footprint; one still in land
    assembly may never build out what it bought.
    """
    if stage >= 8:
        return 1.5
    if stage >= 6:
        return 1.2
    return 1.0


def estimate_power_mw(total_acres: float | None, stage: int) -> ImpactEstimate | None:
    """Estimate power capacity in MW from assembled acreage and development stage.

    Args:
        total_acres: Assembled site acreage, or None when unknown.
        stage: Current development stage, used only for the density multiplier.

    Returns:
        A ranged estimate, or None when there is no acreage to work from.
    """
    if total_acres is None or total_acres <= 0:
        return None

    acres = float(total_acres)
    multiplier = _stage_density_multiplier(stage)

    return ImpactEstimate(
        lower=round(acres * MW_PER_ACRE_LOW * multiplier, 1),
        likely=round(acres * MW_PER_ACRE_LIKELY * multiplier, 1),
        upper=round(acres * MW_PER_ACRE_HIGH * multiplier, 1),
        unit="MW",
        method="Assembled acreage x assumed power density, adjusted for stage",
        assumptions={
            "total_acres": round(acres, 4),
            "mw_per_acre_low": MW_PER_ACRE_LOW,
            "mw_per_acre_likely": MW_PER_ACRE_LIKELY,
            "mw_per_acre_high": MW_PER_ACRE_HIGH,
            "stage": stage,
            "stage_density_multiplier": multiplier,
            "note": (
                "Power density is an industry assumption, not a property of this "
                "site. Helios does not know the building footprint, rack density "
                "or how much of the assembled land will be built on."
            ),
        },
    )


def estimate_water_gpd(power: ImpactEstimate | None) -> ImpactEstimate | None:
    """Estimate cooling water in gallons per day from a power estimate.

    The bounds compound deliberately: the low end pairs the low power figure with
    the most efficient cooling, the high end pairs the high power figure with the
    least. Presenting a narrower band would understate how little is known.

    Args:
        power: The site's power estimate, or None.

    Returns:
        A ranged estimate, or None when there is no power estimate to work from.
    """
    if power is None or power.likely <= 0:
        return None

    def gpd(mw: float, gal_per_kwh: float) -> float:
        return round(mw * _KW_PER_MW * _HOURS_PER_DAY * gal_per_kwh, 1)

    return ImpactEstimate(
        lower=gpd(power.lower, GAL_PER_KWH_LOW),
        likely=gpd(power.likely, GAL_PER_KWH_LIKELY),
        upper=gpd(power.upper, GAL_PER_KWH_HIGH),
        unit="GPD",
        method="Estimated power x assumed cooling water intensity",
        assumptions={
            "power_mw_lower": power.lower,
            "power_mw_likely": power.likely,
            "power_mw_upper": power.upper,
            "gal_per_kwh_low": GAL_PER_KWH_LOW,
            "gal_per_kwh_likely": GAL_PER_KWH_LIKELY,
            "gal_per_kwh_high": GAL_PER_KWH_HIGH,
            "note": (
                "Cooling type is not recorded in any source Helios ingests. A "
                "closed-loop or air-cooled design approaches zero water use; "
                "evaporative cooling can exceed a gallon per kWh. The band is "
                "wide because the practice is."
            ),
        },
    )


def annualise_power_mwh(
    lower_mw: float, likely_mw: float, upper_mw: float
) -> ImpactEstimate | None:
    """Convert a power capacity band in MW to annual energy in MWh.

    Exists for one purpose: reported area electricity totals are published as
    energy over a year, and Helios's site figures are capacity. Comparing them
    without this conversion would be a unit error dressed up as a finding.

    The conversion is not free. It layers an assumed load factor on top of an
    already-inferred MW figure, so the result is weaker than its input and must
    never be rendered as anything but ``inferred``.

    Args:
        lower_mw: Lower bound of the capacity band.
        likely_mw: Central capacity figure.
        upper_mw: Upper bound of the capacity band.

    Returns:
        A ranged annual-energy estimate, or None when there is no capacity.
    """
    if likely_mw <= 0:
        return None

    def mwh(mw: float, load_factor: float) -> float:
        return round(mw * _HOURS_PER_YEAR * load_factor, 1)

    return ImpactEstimate(
        lower=mwh(lower_mw, LOAD_FACTOR_LOW),
        likely=mwh(likely_mw, LOAD_FACTOR_LIKELY),
        upper=mwh(upper_mw, LOAD_FACTOR_HIGH),
        unit="MWh/yr",
        method="Estimated capacity x hours per year x assumed load factor",
        assumptions={
            "power_mw_lower": lower_mw,
            "power_mw_likely": likely_mw,
            "power_mw_upper": upper_mw,
            "hours_per_year": _HOURS_PER_YEAR,
            "load_factor_low": LOAD_FACTOR_LOW,
            "load_factor_likely": LOAD_FACTOR_LIKELY,
            "load_factor_high": LOAD_FACTOR_HIGH,
            "note": (
                "Capacity is not consumption. This converts one to the other so "
                "it can be set beside a reported energy total, and inherits every "
                "assumption in the capacity estimate before adding its own."
            ),
        },
    )


__all__ = [
    "GAL_PER_KWH_HIGH",
    "GAL_PER_KWH_LIKELY",
    "GAL_PER_KWH_LOW",
    "LOAD_FACTOR_HIGH",
    "LOAD_FACTOR_LIKELY",
    "LOAD_FACTOR_LOW",
    "MW_PER_ACRE_HIGH",
    "MW_PER_ACRE_LIKELY",
    "MW_PER_ACRE_LOW",
    "ImpactEstimate",
    "annualise_power_mwh",
    "estimate_power_mw",
    "estimate_water_gpd",
]
