"""Address normalization and parcel matching for address-only sources.

City open-data portals often publish permits with a situs string and no
coordinates. Matching those strings onto assessor parcels is inherently fuzzy;
this module keeps the rules explicit, conservative, and tested so a bad match
cannot silently invent a campus.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from helios_domain.models import Parcel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_UNIT_PATTERN = re.compile(
    r"\s+(?:#|APT|APARTMENT|STE|SUITE|UNIT|BLDG|BUILDING|FL|FLOOR)\s*.*$",
    re.IGNORECASE,
)
_TRAILING_UNIT = re.compile(r"\s+\d{1,6}$")
_NON_ALNUM = re.compile(r"[^A-Z0-9 ]+")
_SPACE = re.compile(r"\s+")

_STREET_TYPES: dict[str, str] = {
    "ROAD": "RD",
    "RD": "RD",
    "STREET": "ST",
    "ST": "ST",
    "AVENUE": "AVE",
    "AVE": "AVE",
    "AV": "AVE",
    "BOULEVARD": "BLVD",
    "BLVD": "BLVD",
    "DRIVE": "DR",
    "DR": "DR",
    "LANE": "LN",
    "LN": "LN",
    "COURT": "CT",
    "CT": "CT",
    "CIRCLE": "CIR",
    "CIR": "CIR",
    "PLACE": "PL",
    "PL": "PL",
    "TERRACE": "TER",
    "TER": "TER",
    "TERR": "TER",
    "WAY": "WAY",
    "PARKWAY": "PKWY",
    "PKWY": "PKWY",
    "HIGHWAY": "HWY",
    "HWY": "HWY",
}

_DIRECTIONS: dict[str, str] = {
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
    "N": "N",
    "S": "S",
    "E": "E",
    "W": "W",
    "NE": "NE",
    "NW": "NW",
    "SE": "SE",
    "SW": "SW",
}


@dataclass(frozen=True, slots=True)
class NormalizedAddress:
    """A reduced address used as a blocking key for parcel matching."""

    house_number: str
    street_name: str
    street_type: str
    direction: str | None
    city: str | None
    raw: str

    @property
    def key(self) -> str:
        """Stable match key excluding city (city is applied as a soft filter)."""
        parts = [self.house_number]
        if self.direction:
            parts.append(self.direction)
        parts.extend([self.street_name, self.street_type])
        return " ".join(p for p in parts if p)


@dataclass(frozen=True, slots=True)
class AddressMatch:
    """A parcel matched to an address string."""

    parcel_id: uuid.UUID
    apn: str
    match_method: str
    confidence: float
    normalized_query: str
    normalized_parcel: str


def normalize_address(value: str | None, *, city: str | None = None) -> NormalizedAddress | None:
    """Normalize a free-text US situs address for exact-key matching.

    Args:
        value: Raw address string.
        city: Optional city hint preserved on the result.

    Returns:
        Normalized components, or ``None`` when the string is not parseable.
    """
    if not value or not str(value).strip():
        return None

    text = str(value).upper().strip()
    text = _UNIT_PATTERN.sub("", text)
    text = _NON_ALNUM.sub(" ", text)
    text = _SPACE.sub(" ", text).strip()
    # Drop a bare trailing unit number left after suite tokens were removed.
    text = _TRAILING_UNIT.sub("", text).strip()
    tokens = text.split()
    if len(tokens) < 2 or not tokens[0][0].isdigit():
        return None

    house = tokens[0]
    rest = tokens[1:]
    direction: str | None = None
    if rest and rest[0] in _DIRECTIONS:
        direction = _DIRECTIONS[rest[0]]
        rest = rest[1:]

    street_type = ""
    if rest and rest[-1] in _STREET_TYPES:
        street_type = _STREET_TYPES[rest[-1]]
        rest = rest[:-1]
    if not rest:
        return None

    street_name = " ".join(_DIRECTIONS.get(tok, tok) for tok in rest)
    return NormalizedAddress(
        house_number=house,
        street_name=street_name,
        street_type=street_type,
        direction=direction,
        city=city.upper().strip() if city else None,
        raw=str(value).strip(),
    )


def find_parcels_by_address(
    session: Session,
    address: str,
    *,
    city: str | None = None,
    limit: int = 5,
) -> list[AddressMatch]:
    """Find parcels whose situs address normalizes to the same key.

    Matching is exact on the normalized key. Helios does not fuzzy-match street
    names: a near-miss is refused rather than attached to the wrong campus.

    Args:
        session: Open database session.
        address: Candidate address from a permit or filing.
        city: Optional city filter (case-insensitive).
        limit: Maximum matches returned.

    Returns:
        Matches ordered by confidence descending.
    """
    query = normalize_address(address, city=city)
    if query is None:
        return []

    statement = select(Parcel).where(Parcel.situs_address.is_not(None))
    if city:
        statement = statement.where(Parcel.situs_city.ilike(city))

    matches: list[AddressMatch] = []
    for parcel in session.scalars(statement):
        normalized = normalize_address(parcel.situs_address, city=parcel.situs_city)
        if normalized is None:
            continue
        if normalized.key != query.key:
            continue
        confidence = 0.92
        method = "address_normalized_exact"
        if city and parcel.situs_city and parcel.situs_city.upper() != city.upper():
            confidence = 0.75
            method = "address_normalized_cross_city"
        matches.append(
            AddressMatch(
                parcel_id=parcel.id,
                apn=parcel.apn,
                match_method=method,
                confidence=confidence,
                normalized_query=query.key,
                normalized_parcel=normalized.key,
            )
        )
        if len(matches) >= limit:
            break

    return sorted(matches, key=lambda item: item.confidence, reverse=True)


__all__ = [
    "AddressMatch",
    "NormalizedAddress",
    "find_parcels_by_address",
    "normalize_address",
]
