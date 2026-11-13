"""The scoring rubric, applied in code so a score never depends on the model's opinion."""

from __future__ import annotations

from leadgen.config import RuleBook
from leadgen.models import ExtractedFields, ScoreResult


def location_fit(location: str | None, rulebook: RuleBook) -> str:
    if not location or not location.strip():
        return "unknown"
    text = location.lower()
    # Nearby first: "Kasur, near Lahore" is a nearby town, not the core city.
    if any(place in text for place in rulebook.service_area.nearby):
        return "nearby"
    if any(place in text for place in rulebook.service_area.core):
        return "core"
    return "outside"


def score_fields(fields: ExtractedFields, rulebook: RuleBook) -> ScoreResult:
    """Add up the rubric points and clamp to the allowed range."""
    scoring = rulebook.scoring
    rubric = scoring.rubric

    bill_points = 0
    if fields.monthly_bill_pkr is not None:
        for band in sorted(rubric.monthly_bill_pkr, key=lambda b: b.min, reverse=True):
            if fields.monthly_bill_pkr >= band.min:
                bill_points = band.points
                break

    fit = location_fit(fields.location, rulebook)
    breakdown = {
        "property_type": rubric.property_type.get(fields.property_type, 0),
        "monthly_bill": bill_points,
        "location_fit": rubric.location.get(fit, 0),
        "timeline": rubric.timeline.get(fields.timeline, 0),
        "quote_requested": rubric.quote_requested if fields.quote_requested else 0,
    }
    score = max(scoring.min_score, min(scoring.max_score, sum(breakdown.values())))
    return ScoreResult(
        score=score,
        is_hot=score >= scoring.hot_threshold,
        breakdown=breakdown,
        location_fit=fit,  # type: ignore[arg-type]
    )
