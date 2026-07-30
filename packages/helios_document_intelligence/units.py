"""Unit parsing and normalization for infrastructure quantities.

Public records express the same physical quantity a dozen ways: "250 MW",
"250,000 kW", "approximately 250 megawatts". Helios normalises to a canonical
unit per dimension while **always retaining the original text and unit**, so an
analyst can see that a stored ``250.0 MW`` came from the phrase "approximately
250 megawatts" and judge the hedging for themselves.

Canonical units:

===============  ==============
Dimension        Canonical unit
===============  ==============
power            MW
apparent power   MVA
voltage          kV
area (land)      acres
area (building)  square feet
water volume     acre-feet
water flow       gallons per day
===============  ==============
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

SQFT_PER_ACRE = 43_560.0
GALLONS_PER_ACRE_FOOT = 325_851.0


class Dimension(StrEnum):
    """Physical dimensions Helios normalises."""

    POWER = "power"
    APPARENT_POWER = "apparent_power"
    VOLTAGE = "voltage"
    LAND_AREA = "land_area"
    BUILDING_AREA = "building_area"
    WATER_VOLUME = "water_volume"
    WATER_FLOW = "water_flow"
    COUNT = "count"


CANONICAL_UNITS: dict[Dimension, str] = {
    Dimension.POWER: "MW",
    Dimension.APPARENT_POWER: "MVA",
    Dimension.VOLTAGE: "kV",
    Dimension.LAND_AREA: "acres",
    Dimension.BUILDING_AREA: "sqft",
    Dimension.WATER_VOLUME: "acre-feet",
    Dimension.WATER_FLOW: "gpd",
    Dimension.COUNT: "count",
}

# Multiplier converting a recognised unit into its canonical unit.
_UNIT_TABLE: dict[str, tuple[Dimension, float]] = {
    # power
    "w": (Dimension.POWER, 1e-6),
    "watt": (Dimension.POWER, 1e-6),
    "watts": (Dimension.POWER, 1e-6),
    "kw": (Dimension.POWER, 1e-3),
    "kilowatt": (Dimension.POWER, 1e-3),
    "kilowatts": (Dimension.POWER, 1e-3),
    "mw": (Dimension.POWER, 1.0),
    "megawatt": (Dimension.POWER, 1.0),
    "megawatts": (Dimension.POWER, 1.0),
    "gw": (Dimension.POWER, 1e3),
    "gigawatt": (Dimension.POWER, 1e3),
    "gigawatts": (Dimension.POWER, 1e3),
    # apparent power
    "kva": (Dimension.APPARENT_POWER, 1e-3),
    "mva": (Dimension.APPARENT_POWER, 1.0),
    "megavolt-ampere": (Dimension.APPARENT_POWER, 1.0),
    "megavolt-amperes": (Dimension.APPARENT_POWER, 1.0),
    # voltage
    "v": (Dimension.VOLTAGE, 1e-3),
    "volt": (Dimension.VOLTAGE, 1e-3),
    "volts": (Dimension.VOLTAGE, 1e-3),
    "kv": (Dimension.VOLTAGE, 1.0),
    "kilovolt": (Dimension.VOLTAGE, 1.0),
    "kilovolts": (Dimension.VOLTAGE, 1.0),
    # land area
    "acre": (Dimension.LAND_AREA, 1.0),
    "acres": (Dimension.LAND_AREA, 1.0),
    "hectare": (Dimension.LAND_AREA, 2.47105),
    "hectares": (Dimension.LAND_AREA, 2.47105),
    # building area
    "sf": (Dimension.BUILDING_AREA, 1.0),
    "sqft": (Dimension.BUILDING_AREA, 1.0),
    "sq ft": (Dimension.BUILDING_AREA, 1.0),
    "square foot": (Dimension.BUILDING_AREA, 1.0),
    "square feet": (Dimension.BUILDING_AREA, 1.0),
    "sqm": (Dimension.BUILDING_AREA, 10.7639),
    "square meters": (Dimension.BUILDING_AREA, 10.7639),
    # water volume
    "acre-foot": (Dimension.WATER_VOLUME, 1.0),
    "acre-feet": (Dimension.WATER_VOLUME, 1.0),
    "af": (Dimension.WATER_VOLUME, 1.0),
    "gallon": (Dimension.WATER_VOLUME, 1.0 / GALLONS_PER_ACRE_FOOT),
    "gallons": (Dimension.WATER_VOLUME, 1.0 / GALLONS_PER_ACRE_FOOT),
    # water flow
    "gpd": (Dimension.WATER_FLOW, 1.0),
    "gallons per day": (Dimension.WATER_FLOW, 1.0),
    "mgd": (Dimension.WATER_FLOW, 1e6),
    "million gallons per day": (Dimension.WATER_FLOW, 1e6),
    "gpm": (Dimension.WATER_FLOW, 1440.0),
    "gallons per minute": (Dimension.WATER_FLOW, 1440.0),
}

_NUMBER = r"(?P<number>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_UNIT_ALTERNATION = "|".join(re.escape(u) for u in sorted(_UNIT_TABLE, key=len, reverse=True))
_QUANTITY_PATTERN = re.compile(
    rf"{_NUMBER}\s*[-\s]?\s*(?P<unit>{_UNIT_ALTERNATION})\b",
    re.IGNORECASE,
)

_HEDGE_WORDS = (
    "approximately",
    "approx",
    "about",
    "up to",
    "as much as",
    "estimated",
    "roughly",
    "nearly",
    "in excess of",
    "over",
    "at least",
)


@dataclass(frozen=True, slots=True)
class Quantity:
    """A parsed quantity retaining both original and normalized representations."""

    value: float
    unit: str
    dimension: Dimension
    raw_text: str
    raw_unit: str
    is_hedged: bool = False
    """True when the source qualified the figure ("approximately 250 MW")."""

    start_offset: int | None = None
    end_offset: int | None = None

    @property
    def confidence(self) -> float:
        """Extraction confidence, reduced when the source hedged the number."""
        return 0.7 if self.is_hedged else 0.9


def parse_number(text: str) -> float | None:
    """Parse a number that may contain thousands separators.

    Args:
        text: Numeric text such as ``"1,250.5"``.

    Returns:
        The float value, or ``None`` if unparseable.
    """
    try:
        return float(text.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def convert(value: float, from_unit: str) -> tuple[float, str, Dimension] | None:
    """Convert a value into its canonical unit.

    Args:
        value: Magnitude in ``from_unit``.
        from_unit: A recognised unit string, case-insensitive.

    Returns:
        ``(canonical_value, canonical_unit, dimension)``, or ``None`` when the
        unit is unrecognised.
    """
    entry = _UNIT_TABLE.get(from_unit.strip().lower())
    if entry is None:
        return None
    dimension, multiplier = entry
    return value * multiplier, CANONICAL_UNITS[dimension], dimension


def _preceding_hedge(text: str, start: int, window: int = 40) -> bool:
    """Detect a hedging phrase shortly before a quantity."""
    prefix = text[max(0, start - window) : start].lower()
    return any(word in prefix for word in _HEDGE_WORDS)


def extract_quantities(text: str, dimensions: set[Dimension] | None = None) -> list[Quantity]:
    """Find every recognisable quantity in free text.

    Args:
        text: Source text.
        dimensions: Restrict results to these dimensions; ``None`` accepts all.

    Returns:
        Quantities in order of appearance, each normalized to its canonical unit.
    """
    if not text:
        return []

    results: list[Quantity] = []
    for match in _QUANTITY_PATTERN.finditer(text):
        number = parse_number(match.group("number"))
        if number is None:
            continue
        raw_unit = match.group("unit")
        converted = convert(number, raw_unit)
        if converted is None:
            continue
        value, unit, dimension = converted
        if dimensions is not None and dimension not in dimensions:
            continue
        results.append(
            Quantity(
                value=value,
                unit=unit,
                dimension=dimension,
                raw_text=match.group(0),
                raw_unit=raw_unit,
                is_hedged=_preceding_hedge(text, match.start()),
                start_offset=match.start(),
                end_offset=match.end(),
            )
        )
    return results


def acres_from_sqft(sqft: float) -> float:
    """Convert square feet to acres."""
    return sqft / SQFT_PER_ACRE


def parse_voltage_list(raw: str | None) -> list[float]:
    """Parse an OpenStreetMap ``voltage`` tag into kilovolts.

    OSM records voltage in **volts**, semicolon-delimited for multi-voltage
    sites: ``"500000;230000;69000"``. Values are returned descending.

    Args:
        raw: The raw tag value.

    Returns:
        Voltages in kV, highest first. Empty when nothing parses.
    """
    if not raw:
        return []
    voltages: list[float] = []
    for part in re.split(r"[;,]", raw):
        cleaned = part.strip()
        if not cleaned:
            continue
        number = parse_number(re.sub(r"[^\d.]", "", cleaned))
        if number is None or number <= 0:
            continue
        # Values above 1000 are volts; smaller ones are already kV.
        voltages.append(number / 1000.0 if number >= 1000 else number)
    return sorted(set(voltages), reverse=True)


__all__ = [
    "CANONICAL_UNITS",
    "GALLONS_PER_ACRE_FOOT",
    "SQFT_PER_ACRE",
    "Dimension",
    "Quantity",
    "acres_from_sqft",
    "convert",
    "extract_quantities",
    "parse_number",
    "parse_voltage_list",
]
