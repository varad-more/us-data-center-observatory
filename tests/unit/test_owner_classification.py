"""Tests for owner-name classification and the PII redaction gate.

The sample names here are real strings observed in the Maricopa County Assessor
parcel layer. Names of private individuals are the exact reason this classifier
exists, so a handful are included to prove they are suppressed - they are used
only as classifier inputs and never persisted or displayed by Helios.
"""

from __future__ import annotations

import pytest

from helios_entity_resolution.names import (
    OwnerClassification,
    analyze_owner_name,
    apply_pii_policy,
    detect_legal_form,
    normalize_organization_name,
)

pytestmark = pytest.mark.unit


class TestNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ALIGNED DATA CENTERS CHANDLER PROPCO LLC", "ALIGNED DATA CENTERS CHANDLER"),
            ("Aligned Data Centers Chandler Propco, L.L.C.", "ALIGNED DATA CENTERS CHANDLER"),
            ("PLATYPUS DEVELOPMENT LLC", "PLATYPUS"),
            ("QTS PHOENIX II DC1 LLC", "QTS PHOENIX II DC1"),
            ("CYRUSONE TRS INC", "CYRUSONE TRS"),
            ("", ""),
        ],
    )
    def test_normalizes_to_stable_key(self, raw: str, expected: str) -> None:
        assert normalize_organization_name(raw) == expected

    def test_differently_punctuated_names_share_a_key(self) -> None:
        """Suffix stripping is what makes entity blocking work at all."""
        a = normalize_organization_name("MECP1 MESA 2 LLC")
        b = normalize_organization_name("MECP1 Mesa 2, L.L.C.")
        assert a == b == "MECP1 MESA 2"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("PLATYPUS DEVELOPMENT LLC", "LLC"),
            ("CYRUSONE TRS INC", "INC"),
            ("MICROSOFT CORPORATION", "CORP"),
            ("SDC PHX I LLC", "LLC"),
            ("2016 YVETTE REVOCABLE TRUST", "TRUST"),
            ("JOHN SMITH", None),
        ],
    )
    def test_detects_legal_form(self, raw: str, expected: str | None) -> None:
        assert detect_legal_form(raw) == expected


class TestClassification:
    @pytest.mark.parametrize(
        "raw",
        [
            "ALIGNED DATA CENTERS CHANDLER PROPCO LLC",
            "PLATYPUS DEVELOPMENT LLC",
            "MECP1 MESA 2 LLC",
            "QTS PHOENIX II DC1 LLC",
            "COMPASS DATACENTERS PHX IA LLC",
            "H5 DATA CENTERS CHANDLER LLC",
            "MICROSOFT CORPORATION",
            "CYRUSONE TRS INC",
        ],
    )
    def test_recognises_organizations(self, raw: str) -> None:
        analysis = analyze_owner_name(raw)
        assert analysis.classification is OwnerClassification.ORGANIZATION
        assert not analysis.should_redact
        assert analysis.reasons

    @pytest.mark.parametrize(
        "raw",
        [
            "COX COMMUNICATIONS ARIZONA LLC",
            "ARIZONA PUBLIC SERVICE ELECTRIC CO",
        ],
    )
    def test_recognises_utilities(self, raw: str) -> None:
        assert analyze_owner_name(raw).classification is OwnerClassification.UTILITY

    @pytest.mark.parametrize(
        "raw",
        ["CITY OF MESA", "MARICOPA COUNTY", "MESA UNIFIED SCHOOL DISTRICT", "STATE OF ARIZONA"],
    )
    def test_recognises_government(self, raw: str) -> None:
        analysis = analyze_owner_name(raw)
        assert analysis.classification is OwnerClassification.GOVERNMENT
        assert not analysis.should_redact

    @pytest.mark.parametrize(
        "raw",
        [
            "TRAN THAO NGOC PHUONG",
            "GANTT JODI/KELLY",
            "ANTTI STEVEN G",
            "BOYD GARRENTT R/NAOMI",
            "DAVIDSEN JOSHUA GEORGE/KRISTINE SANTTI",
        ],
    )
    def test_recognises_and_redacts_natural_persons(self, raw: str) -> None:
        analysis = analyze_owner_name(raw)
        assert analysis.classification is OwnerClassification.NATURAL_PERSON
        assert analysis.should_redact

    @pytest.mark.parametrize(
        "raw",
        ["2016 YVETTE MOSSONTTE REVOCABLE TRUST", "BENTTINE FAMILY TRUST", "GANTT JERRY L TR"],
    )
    def test_person_linked_trusts_are_redacted(self, raw: str) -> None:
        """A family trust carries an individual's name and is treated as personal."""
        analysis = analyze_owner_name(raw)
        assert analysis.classification is OwnerClassification.PERSON_LINKED_TRUST
        assert analysis.should_redact

    def test_institutional_trusts_are_not_redacted(self) -> None:
        analysis = analyze_owner_name("ARIZONA LAND TRUST")
        assert analysis.classification is OwnerClassification.ORGANIZATION
        assert not analysis.should_redact

    def test_unrecognised_names_default_to_redaction(self) -> None:
        """The cost asymmetry favours over-redaction, so ambiguity means suppress."""
        analysis = analyze_owner_name("QQZ XYLOPHONE")
        assert analysis.should_redact

    def test_empty_name_is_unknown_and_not_personal(self) -> None:
        analysis = analyze_owner_name(None)
        assert analysis.classification is OwnerClassification.UNKNOWN
        assert not analysis.should_redact


class TestShellIndicators:
    def test_flags_propco_naming(self) -> None:
        analysis = analyze_owner_name("ALIGNED DATA CENTERS CHANDLER PROPCO LLC")
        assert analysis.is_suspected_shell
        assert any("propco" in i for i in analysis.shell_indicators)

    def test_flags_alphanumeric_project_code(self) -> None:
        analysis = analyze_owner_name("MECP1 MESA 2 LLC")
        assert analysis.is_suspected_shell
        assert any("project-code" in i for i in analysis.shell_indicators)

    def test_large_operating_company_is_not_flagged_as_shell(self) -> None:
        analysis = analyze_owner_name("MICROSOFT CORPORATION")
        assert not analysis.is_suspected_shell

    def test_detects_data_center_reference_in_name(self) -> None:
        assert analyze_owner_name("H5 DATA CENTERS CHANDLER LLC").mentions_data_center
        assert not analyze_owner_name("PLATYPUS DEVELOPMENT LLC").mentions_data_center


class TestPiiPolicy:
    def test_suppresses_personal_name_when_enabled(self) -> None:
        analysis = analyze_owner_name("GANTT JODI/KELLY")
        stored, redacted = apply_pii_policy(analysis, redaction_enabled=True)
        assert stored is None
        assert redacted is True

    def test_preserves_organization_name(self) -> None:
        analysis = analyze_owner_name("PLATYPUS DEVELOPMENT LLC")
        stored, redacted = apply_pii_policy(analysis, redaction_enabled=True)
        assert stored == "PLATYPUS DEVELOPMENT LLC"
        assert redacted is False

    def test_policy_can_be_disabled_for_authorised_internal_use(self) -> None:
        analysis = analyze_owner_name("GANTT JODI/KELLY")
        stored, redacted = apply_pii_policy(analysis, redaction_enabled=False)
        assert stored == "GANTT JODI/KELLY"
        assert redacted is False
