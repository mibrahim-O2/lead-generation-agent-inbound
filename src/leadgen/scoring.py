"""Deterministic lead logic: the scoring rubric, extraction hints and what is missing.

All of this runs in code so that a score, a "missing" list or the questions to
ask never depend on the model's opinion.
"""

from __future__ import annotations

import re

from leadgen.config import Band, RuleBook
from leadgen.models import ExtractedFields, Language, Lead, ScoreResult


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


def _band_points(value: int | None, bands: list[Band]) -> int:
    if value is None:
        return 0
    for band in sorted(bands, key=lambda b: b.min, reverse=True):
        if value >= band.min:
            return band.points
    return 0


def score_fields(fields: ExtractedFields, rulebook: RuleBook) -> ScoreResult:
    """Add up the rubric points and clamp to the allowed range."""
    scoring = rulebook.scoring
    rubric = scoring.rubric
    fit = location_fit(fields.location, rulebook)
    breakdown = {
        "property_type": rubric.property_type.get(fields.property_type, 0),
        # Bill and sanctioned load both measure the energy need: the better one counts.
        "energy_size": max(
            _band_points(fields.monthly_bill_pkr, rubric.monthly_bill_pkr),
            _band_points(fields.sanctioned_load_kw, rubric.sanctioned_load_kw),
        ),
        "location_fit": rubric.location.get(fit, 0),
        "timeline": rubric.timeline.get(fields.timeline, 0),
        # A quote and a site visit both show intent: the stronger one counts.
        "intent": max(
            rubric.quote_requested if fields.quote_requested else 0,
            rubric.site_visit_requested if fields.site_visit_requested else 0,
        ),
    }
    score = max(scoring.min_score, min(scoring.max_score, sum(breakdown.values())))
    return ScoreResult(
        score=score,
        is_hot=score >= scoring.hot_threshold,
        breakdown=breakdown,
        location_fit=fit,  # type: ignore[arg-type]
    )


def apply_hints(
    fields: ExtractedFields, message: str, rulebook: RuleBook
) -> tuple[ExtractedFields, list[str]]:
    """Fill fields the model left unknown when the message clearly states them.

    Returns the (possibly updated) fields and the names of the fields filled in.
    A value the model did give is never overridden.
    """
    hints = rulebook.extraction_hints
    update: dict = {}

    def matches(patterns: list[str]) -> bool:
        return any(re.search(p, message, re.IGNORECASE) for p in patterns)

    if fields.property_type == "unknown":
        for value, patterns in hints.property_type.items():
            if matches(patterns):
                update["property_type"] = value
                break
    if not fields.product_interest:
        found = [value for value, patterns in hints.product_interest.items() if matches(patterns)]
        if found:
            update["product_interest"] = found
    if not update:
        return fields, []
    return fields.model_copy(update=update), sorted(update)


def missing_fields(fields: ExtractedFields, lead: Lead, rulebook: RuleBook) -> list[str]:
    """Fields that are truly unknown, in the rule book's question priority order."""
    unknown = set()
    if not lead.email.strip() and not lead.phone.strip():
        unknown.add("contact")
    if fields.monthly_bill_pkr is None and fields.sanctioned_load_kw is None:
        unknown.add("monthly_bill_pkr")
    if not (fields.location or "").strip():
        unknown.add("location")
    if fields.timeline == "unknown":
        unknown.add("timeline")
    if fields.property_type == "unknown":
        unknown.add("property_type")
    if not fields.product_interest:
        unknown.add("product_interest")
    order = [q.field for q in rulebook.qualification_questions]
    ranked = [name for name in order if name in unknown]
    return ranked + sorted(unknown - set(ranked))


def questions_for(missing: list[str], language: Language, rulebook: RuleBook) -> list[str]:
    """The question text for each missing field, in the reply language, already capped."""
    by_field = {q.field: q for q in rulebook.qualification_questions}
    questions = []
    for name in missing:
        question = by_field.get(name)
        if question is None:
            continue
        local = question.question_roman_urdu if language != "english" else ""
        questions.append(local or question.question)
    return questions[: rulebook.tone.max_questions]
