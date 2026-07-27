"""Assertion classes must stay inside the closed vocabulary.

The whole product rests on a reader being able to tell a reported fact from a
derived one, and the UI picks its badge straight from this string. A model that
stores a class outside the vocabulary therefore renders as an unstyled or absent
badge - an inference that no longer looks like an inference. This guards the
column defaults that feed the API.
"""

from __future__ import annotations

import pytest

from helios_common.vocabulary import AssertionClass
from helios_domain.models import SiteEstimate

pytestmark = pytest.mark.unit

VALID = {str(member) for member in AssertionClass}


def _column_default(model: type, column_name: str) -> str:
    """Return a column's Python-side scalar default."""
    default = model.__table__.columns[column_name].default
    assert default is not None, f"{model.__name__}.{column_name} has no default"
    return str(default.arg)


class TestAssertionClassDefaults:
    def test_site_estimate_default_is_in_the_vocabulary(self) -> None:
        assert _column_default(SiteEstimate, "assertion_class") in VALID

    def test_site_estimate_is_inferred_not_calculated(self) -> None:
        """Power and water estimates apply assumed coefficients, not stored facts.

        Calling them ``calculated`` would imply the number follows from recorded
        values the way acreage follows from geometry. It does not: change the
        assumed MW-per-acre and the answer changes.
        """
        assert _column_default(SiteEstimate, "assertion_class") == str(AssertionClass.INFERRED)


class TestVocabularyIsClosed:
    def test_estimated_is_not_an_assertion_class(self) -> None:
        """Guards the specific drift this test was written for."""
        assert "estimated" not in VALID

    def test_every_member_is_lowercase_single_word(self) -> None:
        """The frontend enum mirrors these strings verbatim."""
        for value in VALID:
            assert value.islower()
            assert " " not in value
