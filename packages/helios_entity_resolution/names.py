"""Organization name normalization and natural-person classification.

Two jobs live here, both driven by the same problem: county assessor records
express ownership as a single unstructured string, and that string is sometimes
a company and sometimes a private citizen.

**Normalization** produces a stable blocking key so that ``ALIGNED DATA CENTERS
CHANDLER PROPCO LLC`` and ``Aligned Data Centers Chandler Propco, L.L.C.``
resolve to one entity.

**Classification** decides whether a name denotes an organization or a natural
person. This is the gate for Helios's PII policy: names classified as natural
persons, and trusts named after individuals, are redacted before they are ever
written to the database. The classifier is intentionally biased toward
redaction - a company wrongly redacted costs a little recall, while a private
homeowner wrongly published is a serious harm.

Every classification returns the reasons behind it, so a reviewer can audit why
a particular name was suppressed or kept.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache

CORPORATE_SUFFIXES: frozenset[str] = frozenset(
    {
        "LLC",
        "L L C",
        "LLP",
        "LP",
        "LLLP",
        "INC",
        "INCORPORATED",
        "CORP",
        "CORPORATION",
        "CO",
        "COMPANY",
        "LTD",
        "LIMITED",
        "PLC",
        "LC",
        "PC",
        "PA",
        "PLLC",
        "PARTNERSHIP",
        "PARTNERS",
        "ASSOCIATES",
        "ASSOCIATION",
        "ASSN",
        "HOLDINGS",
        "HOLDING",
        "PROPCO",
        "OPCO",
        "REIT",
        "FUND",
        "CAPITAL",
        "VENTURES",
        "GROUP",
        "ENTERPRISES",
        "INDUSTRIES",
        "PROPERTIES",
        "DEVELOPMENT",
        "DEVELOPMENTS",
        "INVESTMENTS",
        "INVESTMENT",
    }
)
"""Tokens that, when present, make a name almost certainly an organization."""

GOVERNMENT_MARKERS: tuple[str, ...] = (
    "CITY OF",
    "TOWN OF",
    "COUNTY OF",
    "STATE OF",
    "UNITED STATES",
    "US DEPT",
    "DEPARTMENT OF",
    "DISTRICT",
    "MUNICIPAL",
    "AUTHORITY",
    "COMMISSION",
    "SCHOOL DIST",
    "UNIFIED SCHOOL",
    "FLOOD CONTROL",
    "MARICOPA COUNTY",
    "SALT RIVER PROJECT",
    "BUREAU OF",
)
"""Note that "PUBLIC SERVICE" is deliberately absent: Arizona Public Service is an
investor-owned utility, not a government body, and the phrase is too ambiguous to use."""

UTILITY_MARKERS: tuple[str, ...] = (
    "ELECTRIC",
    "POWER",
    "UTILITY",
    "UTILITIES",
    "ENERGY",
    "GAS COMPANY",
    "WATER COMPANY",
    "IRRIGATION",
    "TELECOM",
    "COMMUNICATIONS",
)

DATA_CENTER_MARKERS: tuple[str, ...] = (
    "DATA CENTER",
    "DATA CENTRE",
    "DATACENTER",
    "DATACENTRE",
    "COLOCATION",
    "HYPERSCALE",
    "CLOUD",
)

TRUST_MARKERS: tuple[str, ...] = (
    "TRUST",
    "TR",
    "REVOCABLE",
    "IRREVOCABLE",
    "LIVING TRUST",
    "FAMILY TRUST",
    "ESTATE OF",
    "LIFE ESTATE",
)

_INSTITUTIONAL_TRUST_MARKERS: tuple[str, ...] = (
    "BUSINESS TRUST",
    "STATUTORY TRUST",
    "REAL ESTATE INVESTMENT TRUST",
    "LAND TRUST",
    "PENSION TRUST",
    "CHARITABLE TRUST",
)

_LEGAL_FORM_PATTERN = re.compile(
    r"\b(LLC|L\.?L\.?C\.?|LLLP|LLP|LP|INC|CORP|CORPORATION|CO|COMPANY|LTD|PLLC|PC|TRUST)\b"
)

_PUNCTUATION = re.compile(r"[.,'\"()]")
_WHITESPACE = re.compile(r"\s+")
_DOTTED_ACRONYM = re.compile(r"\b(?:[A-Za-z]\.){2,}")
"""Matches ``L.L.C.`` and ``P.C.`` so they collapse to ``LLC`` before tokenizing."""
_MULTI_PERSON = re.compile(r"[/&]| AND ")
"""Assessors join co-owners with slashes or ampersands: ``GANTT JODI/KELLY``."""

_PERSON_PARTICLES: frozenset[str] = frozenset(
    {"JR", "SR", "II", "III", "IV", "MR", "MRS", "MS", "DR", "TR", "TRUSTEE", "ETAL", "ET AL"}
)


class OwnerClassification(StrEnum):
    """What kind of party an owner-name string denotes."""

    ORGANIZATION = "organization"
    GOVERNMENT = "government"
    UTILITY = "utility"
    NATURAL_PERSON = "natural_person"
    PERSON_LINKED_TRUST = "person_linked_trust"
    """A trust or estate bearing an individual's name. Redacted like a person."""

    UNKNOWN = "unknown"

    @property
    def is_personal(self) -> bool:
        """Whether PII policy should suppress this name."""
        return self in {
            OwnerClassification.NATURAL_PERSON,
            OwnerClassification.PERSON_LINKED_TRUST,
        }


@dataclass(frozen=True, slots=True)
class OwnerAnalysis:
    """The result of analysing an owner-name string."""

    raw_name: str
    normalized_name: str
    classification: OwnerClassification
    confidence: float
    legal_form: str | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)
    is_suspected_shell: bool = False
    shell_indicators: tuple[str, ...] = field(default_factory=tuple)
    mentions_data_center: bool = False

    @property
    def should_redact(self) -> bool:
        """Whether this name must be suppressed under the PII policy."""
        return self.classification.is_personal


def _canonicalize(name: str) -> str:
    """Upper-case, collapse dotted acronyms, and strip punctuation and whitespace.

    Dotted acronyms are collapsed *before* punctuation is stripped, otherwise
    ``L.L.C.`` becomes three separate ``L``/``L``/``C`` tokens that match no
    known suffix.
    """
    text = _DOTTED_ACRONYM.sub(lambda m: m.group(0).replace(".", ""), name.upper())
    text = _PUNCTUATION.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def normalize_organization_name(name: str) -> str:
    """Produce a stable comparison key for an organization name.

    Upper-cases, strips punctuation and legal-form suffixes, and collapses
    whitespace. Suffix stripping is what allows ``Acme Holdings, LLC`` and
    ``ACME HOLDINGS L.L.C.`` to block together during entity resolution.

    Args:
        name: Raw name as printed by the source.

    Returns:
        The normalized key. Empty input yields an empty string.
    """
    if not name:
        return ""
    text = _canonicalize(name)

    tokens = text.split(" ")
    while tokens and tokens[-1] in CORPORATE_SUFFIXES:
        tokens.pop()
    # A name consisting only of suffix tokens (rare, malformed) keeps its
    # original form rather than collapsing to nothing.
    return " ".join(tokens) if tokens else text


def detect_legal_form(name: str) -> str | None:
    """Extract the legal form from a name, if one is stated.

    Args:
        name: Raw or normalized name.

    Returns:
        A canonical legal form such as ``LLC``, or ``None``.
    """
    if not name:
        return None
    match = _LEGAL_FORM_PATTERN.search(_canonicalize(name))
    if not match:
        return None
    form = match.group(1).replace(".", "")
    return {"CORPORATION": "CORP", "COMPANY": "CO", "LLC": "LLC"}.get(form, form)


@lru_cache(maxsize=256)
def _marker_pattern(markers: tuple[str, ...]) -> re.Pattern[str]:
    """Compile a word-boundary alternation for a marker set.

    Word boundaries are essential rather than cosmetic. Plain substring matching
    classified ``TRAN THAO NGOC PHUONG`` as a trust because the trustee
    abbreviation ``TR`` appears inside the surname, and the same flaw made a
    supplier search match ``GANTT`` for ``NTT``.
    """
    alternation = "|".join(re.escape(m) for m in sorted(markers, key=len, reverse=True))
    # A trailing ``S?`` lets one marker cover both "DATA CENTER" and "DATA CENTERS"
    # without duplicating every entry in the marker lists.
    return re.compile(rf"(?<![A-Z0-9])(?:{alternation})S?(?![A-Z0-9])")


def _contains_any(text: str, markers: tuple[str, ...]) -> str | None:
    """Return the first whole-word marker found in text, or ``None``."""
    match = _marker_pattern(markers).search(text)
    return match.group(0) if match else None


def _looks_like_person_name(text: str) -> bool:
    """Heuristic for the assessor's ``SURNAME GIVEN MIDDLE`` convention.

    Applied only after corporate and government markers have been ruled out.
    """
    tokens = [t for t in text.split() if t and t not in _PERSON_PARTICLES]
    if not 2 <= len(tokens) <= 5:
        return False
    # Digits appear in entity names (``MECP1 MESA 2``) but essentially never in
    # a person's name as recorded by the assessor.
    return all(token.isalpha() for token in tokens)


def analyze_owner_name(name: str | None) -> OwnerAnalysis:
    """Classify an owner-name string and derive its normalization.

    The classifier runs a fixed ladder of tests, most decisive first, and records
    every test that fired so the outcome can be audited:

    1. Government markers.
    2. Corporate suffixes and utility markers.
    3. Institutional versus person-linked trusts.
    4. Multi-party separators (``/``, ``&``) indicating co-owning individuals.
    5. The assessor's personal-name shape.

    Anything still unresolved is treated as a natural person, because an
    unclassifiable name is more likely to be an individual than a company, and
    the cost asymmetry favours redaction.

    Args:
        name: Raw owner name, possibly ``None`` or blank.

    Returns:
        The analysis, including confidence and the reasons that drove it.
    """
    if not name or not name.strip():
        return OwnerAnalysis(
            raw_name=name or "",
            normalized_name="",
            classification=OwnerClassification.UNKNOWN,
            confidence=0.0,
            reasons=("empty name",),
        )

    raw = name.strip()
    upper = _canonicalize(raw)
    normalized = normalize_organization_name(raw)
    legal_form = detect_legal_form(raw)
    reasons: list[str] = []

    mentions_dc = _contains_any(upper, DATA_CENTER_MARKERS) is not None
    if mentions_dc:
        reasons.append("name references data-center activity")

    if marker := _contains_any(upper, GOVERNMENT_MARKERS):
        reasons.append(f"government marker {marker!r}")
        return OwnerAnalysis(
            raw_name=raw,
            normalized_name=normalized,
            classification=OwnerClassification.GOVERNMENT,
            confidence=0.95,
            legal_form=legal_form,
            reasons=tuple(reasons),
            mentions_data_center=mentions_dc,
        )

    tokens = set(upper.split())
    corporate_tokens = tokens & CORPORATE_SUFFIXES
    # ``TR`` is a trustee abbreviation, not a corporate form; exclude the bare
    # ``CO`` token too when it is part of a person's name is not a real risk, but
    # a standalone ``CO`` with no other corporate signal is weak evidence.
    has_corporate = bool(corporate_tokens) or legal_form not in (None, "TRUST")

    if has_corporate:
        if corporate_tokens:
            reasons.append(f"corporate token(s) {sorted(corporate_tokens)}")
        if legal_form and legal_form != "TRUST":
            reasons.append(f"legal form {legal_form!r}")

        if utility_marker := _contains_any(upper, UTILITY_MARKERS):
            reasons.append(f"utility marker {utility_marker!r}")
            classification = OwnerClassification.UTILITY
        else:
            classification = OwnerClassification.ORGANIZATION

        shell_indicators = _shell_indicators(upper, legal_form)
        return OwnerAnalysis(
            raw_name=raw,
            normalized_name=normalized,
            classification=classification,
            confidence=0.93,
            legal_form=legal_form,
            reasons=tuple(reasons),
            is_suspected_shell=bool(shell_indicators),
            shell_indicators=tuple(shell_indicators),
            mentions_data_center=mentions_dc,
        )

    if trust_marker := _contains_any(upper, TRUST_MARKERS):
        if institutional := _contains_any(upper, _INSTITUTIONAL_TRUST_MARKERS):
            reasons.append(f"institutional trust marker {institutional!r}")
            return OwnerAnalysis(
                raw_name=raw,
                normalized_name=normalized,
                classification=OwnerClassification.ORGANIZATION,
                confidence=0.8,
                legal_form="TRUST",
                reasons=tuple(reasons),
                mentions_data_center=mentions_dc,
            )
        reasons.append(f"trust marker {trust_marker!r} with no institutional qualifier")
        return OwnerAnalysis(
            raw_name=raw,
            normalized_name=normalized,
            classification=OwnerClassification.PERSON_LINKED_TRUST,
            confidence=0.75,
            legal_form="TRUST",
            reasons=tuple(reasons),
            mentions_data_center=mentions_dc,
        )

    if _MULTI_PERSON.search(upper):
        reasons.append("multi-party separator suggests co-owning individuals")
        return OwnerAnalysis(
            raw_name=raw,
            normalized_name=normalized,
            classification=OwnerClassification.NATURAL_PERSON,
            confidence=0.85,
            reasons=tuple(reasons),
        )

    if _looks_like_person_name(upper):
        reasons.append("matches assessor personal-name shape with no organizational marker")
        return OwnerAnalysis(
            raw_name=raw,
            normalized_name=normalized,
            classification=OwnerClassification.NATURAL_PERSON,
            confidence=0.8,
            reasons=tuple(reasons),
        )

    reasons.append("no organizational marker found; defaulting to person for privacy safety")
    return OwnerAnalysis(
        raw_name=raw,
        normalized_name=normalized,
        classification=OwnerClassification.NATURAL_PERSON,
        confidence=0.5,
        reasons=tuple(reasons),
    )


_SHELL_NAME_PATTERN = re.compile(r"\b[A-Z]{2,6}\d{1,3}\b")
"""Alphanumeric codes such as ``MECP1`` that are typical of project-specific entities."""


def _shell_indicators(upper_name: str, legal_form: str | None) -> list[str]:
    """Collect weak signals that an entity is a single-purpose vehicle.

    None of these individually justifies attributing an entity to a parent
    company. They exist to *flag for review*, and the scoring model gives them
    deliberately small weight.

    Args:
        upper_name: Upper-cased, de-punctuated name.
        legal_form: Detected legal form, if any.

    Returns:
        Human-readable indicator strings.
    """
    indicators: list[str] = []
    if legal_form in {"LLC", "LP", "LLLP", "LLP"}:
        indicators.append(f"pass-through legal form ({legal_form})")
    if "PROPCO" in upper_name or "OPCO" in upper_name:
        indicators.append("propco/opco naming convention")
    if _SHELL_NAME_PATTERN.search(upper_name):
        indicators.append("alphanumeric project-code naming pattern")
    if "HOLDINGS" in upper_name or "HOLDING" in upper_name:
        indicators.append("holding-company naming")
    # A very short name with a pass-through form is characteristic of an entity
    # formed for one transaction.
    core_tokens = [t for t in upper_name.split() if t not in CORPORATE_SUFFIXES]
    if len(core_tokens) <= 2 and legal_form in {"LLC", "LP"}:
        indicators.append("minimal descriptive name")
    return indicators


def apply_pii_policy(
    analysis: OwnerAnalysis, *, redaction_enabled: bool = True
) -> tuple[str | None, bool]:
    """Decide what owner name, if any, may be persisted.

    Args:
        analysis: Output of :func:`analyze_owner_name`.
        redaction_enabled: Whether the PII policy is active.

    Returns:
        A tuple of the storable name (``None`` when suppressed) and a flag
        indicating that redaction was applied.
    """
    if redaction_enabled and analysis.should_redact:
        return None, True
    return analysis.raw_name, False


__all__ = [
    "CORPORATE_SUFFIXES",
    "OwnerAnalysis",
    "OwnerClassification",
    "analyze_owner_name",
    "apply_pii_policy",
    "detect_legal_form",
    "normalize_organization_name",
]
