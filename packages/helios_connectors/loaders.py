"""Persistence of normalized connector output into domain tables.

Loaders are the only place where connector output becomes durable state. They
are kept separate from connectors so that a connector can be tested end to end
without a database, and so that the rules governing *how* facts enter the graph
live in one auditable place.

Every loader is an upsert keyed on a natural identifier, which is what makes
repeated ingestion idempotent at the entity level. Evidence records are created
only when a genuinely new document version appears, so re-running an unchanged
source adds nothing to a site's timeline.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from geoalchemy2 import WKTElement
from sqlalchemy import select

from helios_common.logging import get_logger
from helios_common.vocabulary import AssertionClass, EvidencePolarity
from helios_domain.models import (
    DocumentVersion,
    EvidenceRecord,
    Organization,
    OrganizationAlias,
    Parcel,
    ParcelOwnershipEvent,
    Permit,
    Source,
    SourceDocument,
    Substation,
    TransmissionLine,
)
from helios_domain.ontology import OrganizationRole
from helios_entity_resolution.names import OwnerClassification

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from helios_connectors.types import EvidenceItem, ExtractedField, NormalizedRecord

logger = get_logger(__name__)

_SRID = 4326

_CLASSIFICATION_TO_ROLE: dict[str, str] = {
    str(OwnerClassification.ORGANIZATION): str(OrganizationRole.OWNER),
    str(OwnerClassification.UTILITY): str(OrganizationRole.UTILITY),
    str(OwnerClassification.GOVERNMENT): str(OrganizationRole.GOVERNMENT_BODY),
}


def _geom(wkt: str | None) -> WKTElement | None:
    """Wrap WKT in a SRID-tagged geometry element."""
    return WKTElement(wkt, srid=_SRID) if wkt else None


def get_or_create_organization(
    session: Session,
    *,
    canonical_name: str,
    normalized_name: str,
    role: str,
    legal_form: str | None = None,
    is_suspected_shell: bool = False,
    shell_indicators: list[str] | None = None,
    mailing_city: str | None = None,
    mailing_state: str | None = None,
) -> Organization:
    """Resolve an organization by normalized name, creating it if absent.

    Blocking on the normalized name is a deliberately conservative first pass: it
    merges punctuation and suffix variants but will not merge genuinely different
    spellings. Probabilistic matching across weaker signals is a later phase, and
    keeping this step conservative means the graph never silently fuses two
    distinct companies.

    Args:
        session: Open database session.
        canonical_name: Display name as printed by the source.
        normalized_name: Blocking key from the name normalizer.
        role: Domain role for the organization.
        legal_form: Detected legal form.
        is_suspected_shell: Whether shell indicators were found.
        shell_indicators: Human-readable indicator strings.
        mailing_city: Mailing city, for organizations only.
        mailing_state: Mailing state, for organizations only.

    Returns:
        The persisted organization.
    """
    organization = session.scalar(
        select(Organization).where(Organization.normalized_name == normalized_name)
    )
    if organization is None:
        organization = Organization(
            canonical_name=canonical_name,
            normalized_name=normalized_name,
            role=role,
            organization_type=legal_form,
            is_suspected_shell=is_suspected_shell,
            shell_indicators={"indicators": shell_indicators or []},
            mailing_city=mailing_city,
            mailing_state=mailing_state,
        )
        session.add(organization)
        session.flush()
    elif canonical_name != organization.canonical_name:
        _record_alias(session, organization, canonical_name, normalized_name)

    return organization


def _record_alias(
    session: Session, organization: Organization, alias: str, normalized_alias: str
) -> None:
    """Store an alternate spelling if it is not already known."""
    existing = session.scalar(
        select(OrganizationAlias).where(
            OrganizationAlias.organization_id == organization.id,
            OrganizationAlias.normalized_alias == normalized_alias,
        )
    )
    if existing is None:
        session.add(
            OrganizationAlias(
                organization_id=organization.id,
                alias=alias,
                normalized_alias=normalized_alias,
            )
        )


def load_parcel(
    session: Session,
    record: NormalizedRecord,
    *,
    source: Source,
    document: SourceDocument,
    version: DocumentVersion,
    create_evidence: bool,
) -> tuple[Parcel, list[EvidenceRecord]]:
    """Upsert a parcel and its ownership event, optionally recording evidence.

    Args:
        session: Open database session.
        record: Normalized parcel record.
        source: Owning source row.
        document: Source document the record came from.
        version: The specific immutable version cited.
        create_evidence: Whether this version is new and therefore worth citing.

    Returns:
        The parcel and any evidence records created.
    """
    payload = record.payload
    apn = payload["apn"]

    parcel = session.scalar(select(Parcel).where(Parcel.source_id == source.id, Parcel.apn == apn))
    if parcel is None:
        parcel = Parcel(source_id=source.id, apn=apn)
        session.add(parcel)

    owner_analysis = payload.get("owner_analysis") or {}
    organization = _resolve_parcel_owner(session, payload, owner_analysis)

    parcel.apn_formatted = payload.get("apn_formatted")
    parcel.county = payload.get("county", "Maricopa")
    parcel.jurisdiction = payload.get("jurisdiction")
    parcel.situs_address = payload.get("situs_address")
    parcel.situs_city = payload.get("situs_city")
    parcel.situs_postal_code = payload.get("situs_postal_code")
    parcel.owner_name_raw = payload.get("owner_name_raw")
    parcel.owner_is_redacted = bool(payload.get("owner_is_redacted"))
    parcel.owner_organization_id = organization.id if organization else None
    parcel.land_use_code = payload.get("land_use_code")
    parcel.land_use_description = payload.get("land_use_description")
    parcel.legal_class_code = payload.get("legal_class_code")
    parcel.lot_size_acres = payload.get("lot_size_acres")
    parcel.lot_size_sqft = payload.get("lot_size_sqft")
    parcel.construction_year = payload.get("construction_year")
    parcel.last_deed_number = payload.get("last_deed_number")
    parcel.last_deed_date = payload.get("last_deed_date")
    parcel.last_deed_url = payload.get("last_deed_url")
    parcel.last_sale_date = payload.get("last_sale_date")
    parcel.last_sale_price = payload.get("last_sale_price")
    parcel.assessor_url = payload.get("assessor_url")
    parcel.source_document_id = document.id
    parcel.attributes = {"owner_analysis": owner_analysis}

    if record.geometry_wkt:
        parcel.geometry = _geom(record.geometry_wkt)
    if (lat := payload.get("latitude")) is not None and (
        lon := payload.get("longitude")
    ) is not None:
        parcel.centroid = _geom(f"POINT({lon} {lat})")

    session.flush()

    created: list[EvidenceRecord] = []
    if create_evidence:
        created = [
            _create_evidence(
                session,
                item=item,
                document=document,
                version=version,
                parcel_id=parcel.id,
                organization_id=organization.id if organization else None,
            )
            for item in record.evidence
        ]

    _load_ownership_event(session, parcel, payload, created[0] if created else None)
    return parcel, created


def _resolve_parcel_owner(
    session: Session, payload: dict[str, Any], analysis: dict[str, Any]
) -> Organization | None:
    """Create an organization for a parcel owner, unless the owner is a person.

    Natural persons deliberately get no ``organizations`` row at all. Storing a
    redacted placeholder would still leak the existence and parcel linkage of a
    private individual, so the record simply does not exist.
    """
    owner_name = payload.get("owner_name_raw")
    classification = analysis.get("classification")
    if not owner_name or classification not in _CLASSIFICATION_TO_ROLE:
        return None

    normalized = analysis.get("normalized_name")
    if not normalized:
        return None

    return get_or_create_organization(
        session,
        canonical_name=owner_name,
        normalized_name=normalized,
        role=_CLASSIFICATION_TO_ROLE[classification],
        legal_form=analysis.get("legal_form"),
        is_suspected_shell=bool(analysis.get("is_suspected_shell")),
        shell_indicators=list(analysis.get("shell_indicators") or []),
        mailing_city=payload.get("owner_city"),
        mailing_state=payload.get("owner_state"),
    )


def _load_ownership_event(
    session: Session,
    parcel: Parcel,
    payload: dict[str, Any],
    evidence: EvidenceRecord | None,
) -> ParcelOwnershipEvent | None:
    """Record the most recent deed as an ownership event.

    The assessor exposes only the latest deed, so Helios observes a single point
    rather than a chain. The table models full chains; this loader simply cannot
    populate one from this source, which is recorded as a recall limitation.
    """
    event_date = payload.get("last_deed_date")
    if event_date is None:
        return None

    deed_number = payload.get("last_deed_number")
    existing = session.scalar(
        select(ParcelOwnershipEvent).where(
            ParcelOwnershipEvent.parcel_id == parcel.id,
            ParcelOwnershipEvent.event_date == event_date,
            ParcelOwnershipEvent.deed_number == deed_number,
        )
    )
    if existing is not None:
        return existing

    event = ParcelOwnershipEvent(
        parcel_id=parcel.id,
        organization_id=parcel.owner_organization_id,
        event_type="deed_transfer",
        event_date=event_date,
        owner_name_raw=payload.get("owner_name_raw"),
        owner_is_redacted=bool(payload.get("owner_is_redacted")),
        deed_number=deed_number,
        deed_url=payload.get("last_deed_url"),
        sale_price=payload.get("last_sale_price"),
        assertion_class=str(AssertionClass.REPORTED),
        confidence=0.95,
        evidence_record_id=evidence.id if evidence else None,
    )
    session.add(event)
    return event


def load_substation(
    session: Session,
    record: NormalizedRecord,
    *,
    source: Source,
    document: SourceDocument,
) -> Substation:
    """Upsert a substation."""
    payload = record.payload
    native_id = payload["source_native_id"]

    substation = session.scalar(
        select(Substation).where(
            Substation.source_id == source.id,
            Substation.source_native_id == native_id,
        )
    )
    if substation is None:
        substation = Substation(source_id=source.id, source_native_id=native_id)
        session.add(substation)

    substation.name = payload.get("name")
    substation.operator_name = payload.get("operator_name")
    substation.max_voltage_kv = payload.get("max_voltage_kv")
    substation.voltages_kv = payload.get("voltages_kv") or []
    substation.substation_function = payload.get("substation_function")
    substation.status = payload.get("status")
    substation.source_document_id = document.id
    substation.attributes = {"osm_url": payload.get("osm_url")}
    if record.geometry_wkt:
        substation.location = _geom(record.geometry_wkt)

    return substation


def load_permit(
    session: Session,
    record: NormalizedRecord,
    *,
    source: Source,
    document: SourceDocument,
    version: DocumentVersion,
    create_evidence: bool,
) -> tuple[Permit, list[EvidenceRecord]]:
    """Upsert a permit or regulatory filing and optionally create evidence.

    Permits are initially unlinked from sites. Site building attaches nearby
    permits by geometry so connectors do not need to know Helios site codes.
    """
    payload = record.payload
    native_id = str(payload["source_native_id"])

    permit = session.scalar(
        select(Permit).where(
            Permit.source_id == source.id,
            Permit.source_native_id == native_id,
        )
    )
    if permit is None:
        permit = Permit(source_id=source.id, source_native_id=native_id)
        session.add(permit)

    permit.permit_number = payload.get("permit_number")
    permit.category = str(payload.get("category") or "unknown")
    permit.permit_type_raw = payload.get("permit_type_raw")
    permit.description = payload.get("description")
    permit.status = payload.get("status")
    permit.issuing_authority = payload.get("issuing_authority")
    permit.jurisdiction = payload.get("jurisdiction")
    permit.applied_date = payload.get("applied_date")
    permit.issued_date = payload.get("issued_date")
    permit.address_raw = payload.get("address_raw")
    permit.source_document_id = document.id
    permit.attributes = dict(payload.get("attributes") or {})
    if record.geometry_wkt:
        permit.location = _geom(record.geometry_wkt)

    session.flush()

    created: list[EvidenceRecord] = []
    if create_evidence:
        created = [
            _create_evidence(
                session,
                item=item,
                document=document,
                version=version,
                site_id=permit.site_id,
            )
            for item in record.evidence
        ]
        # Stash permit id on evidence via normalized_values for later attachment.
        for evidence in created:
            values = dict(evidence.normalized_values or {})
            values["permit_id"] = str(permit.id)
            evidence.normalized_values = values

    return permit, created


def load_transmission_line(
    session: Session,
    record: NormalizedRecord,
    *,
    source: Source,
    document: SourceDocument,
) -> TransmissionLine:
    """Upsert a transmission line."""
    payload = record.payload
    native_id = payload["source_native_id"]

    line = session.scalar(
        select(TransmissionLine).where(
            TransmissionLine.source_id == source.id,
            TransmissionLine.source_native_id == native_id,
        )
    )
    if line is None:
        line = TransmissionLine(source_id=source.id, source_native_id=native_id)
        session.add(line)

    line.name = payload.get("name")
    line.operator_name = payload.get("operator_name")
    line.voltage_kv = payload.get("voltage_kv")
    line.circuit_count = payload.get("circuit_count")
    line.status = payload.get("status")
    line.source_document_id = document.id
    line.attributes = {
        "osm_url": payload.get("osm_url"),
        "geometry_note": (
            "Overpass 'out center' returns a centroid for ways, so this line is "
            "represented by a point. Distance calculations against it are approximate."
        ),
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
    }
    return line


def _create_evidence(
    session: Session,
    *,
    item: EvidenceItem,
    document: SourceDocument,
    version: DocumentVersion,
    parcel_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
) -> EvidenceRecord:
    """Create an evidence record citing a specific immutable document version."""
    evidence = EvidenceRecord(
        document_id=document.id,
        document_version_id=version.id,
        parcel_id=parcel_id,
        organization_id=organization_id,
        site_id=site_id,
        evidence_kind=item.kind,
        summary=item.summary,
        snippet=item.snippet or _render_fields(item.fields),
        snippet_locator=item.locator,
        observed_at=item.observed_at,
        assertion_class=str(item.assertion_class),
        extraction_method=str(item.extraction_method),
        polarity=str(EvidencePolarity.SUPPORTING),
        confidence=item.confidence,
        parser_version=version.parser_version or "0.1.0",
        normalized_values={
            "fields": [f.to_json() for f in item.fields],
            "is_standing_condition": item.is_standing_condition,
        },
    )
    session.add(evidence)
    session.flush()
    return evidence


def _render_fields(fields: list[ExtractedField]) -> str:
    """Render extracted values as a readable quotation.

    Structured feeds have no prose to quote, so the snippet is a faithful
    rendering of the exact source fields that were read, each labelled with its
    unit. That still answers "show me where you read that".
    """
    parts: list[str] = []
    for extracted in fields:
        if extracted.value is None and extracted.snippet:
            parts.append(extracted.snippet)
            continue
        unit = f" {extracted.normalized_unit}" if extracted.normalized_unit else ""
        parts.append(f"{extracted.name} = {extracted.value}{unit}")
    return "; ".join(parts)


ENTITY_LOADERS = {
    "parcel": load_parcel,
    "substation": load_substation,
    "transmission_line": load_transmission_line,
    "permit": load_permit,
}
"""Dispatch table from ``NormalizedRecord.entity_type`` to its loader."""


__all__ = [
    "ENTITY_LOADERS",
    "get_or_create_organization",
    "load_parcel",
    "load_permit",
    "load_substation",
    "load_transmission_line",
]
