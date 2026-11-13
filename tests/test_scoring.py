from __future__ import annotations

import pytest

from leadgen.models import ExtractedFields
from leadgen.scoring import location_fit, score_fields


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({}, 1),  # nothing known: clamped up to the minimum
        ({"property_type": "home"}, 2),
        ({"property_type": "home", "monthly_bill_pkr": 19_999}, 2),
        ({"property_type": "home", "monthly_bill_pkr": 20_000}, 3),
        ({"property_type": "home", "monthly_bill_pkr": 50_000}, 4),
        ({"property_type": "home", "monthly_bill_pkr": 100_000}, 5),
        ({"property_type": "home", "monthly_bill_pkr": 60_000, "location": "DHA Lahore",
          "timeline": "immediate", "quote_requested": True}, 9),
        ({"property_type": "factory", "monthly_bill_pkr": 1_500_000, "location": "Lahore",
          "timeline": "immediate", "quote_requested": True}, 10),  # 11 points, clamped
        ({"property_type": "farm", "monthly_bill_pkr": 80_000, "location": "near Kasur",
          "timeline": "within_3_months", "quote_requested": True}, 7),
        ({"property_type": "home", "location": "Karachi", "timeline": "later"}, 2),
    ],
)  # fmt: skip
def test_rubric(rulebook, fields: dict, expected: int) -> None:
    assert score_fields(ExtractedFields(**fields), rulebook).score == expected


def test_hot_threshold_and_breakdown(rulebook) -> None:
    hot = score_fields(
        ExtractedFields(property_type="business", monthly_bill_pkr=120_000, location="Gulberg"),
        rulebook,
    )
    assert hot.score == 7 and hot.is_hot
    assert hot.breakdown == {
        "property_type": 2, "monthly_bill": 3, "location_fit": 2, "timeline": 0,
        "quote_requested": 0,
    }  # fmt: skip
    assert not score_fields(ExtractedFields(property_type="business"), rulebook).is_hot


@pytest.mark.parametrize(
    ("location", "fit"),
    [("Lahore", "core"), ("Johar Town", "core"), ("Kasur, near Lahore", "nearby"),
     ("Karachi", "outside"), (None, "unknown"), ("  ", "unknown")],
)  # fmt: skip
def test_location_fit(rulebook, location, fit: str) -> None:
    assert location_fit(location, rulebook) == fit
