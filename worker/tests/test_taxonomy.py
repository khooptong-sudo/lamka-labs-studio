"""The closed vocabularies are the structural defence against the listicle
trap (blueprint §2.2). These tests exist to make widening them loud."""

from app.taxonomy import ARCHETYPES, VERTICALS, is_archetype, is_vertical


def test_archetypes_match_blueprint_section_5():
    assert ARCHETYPES == (
        "explainer",
        "metric_teardown",
        "filing_walkthrough",
        "macro_calendar",
        "concept_comparison",
        "regulatory_update",
        "historical_parallel",
        "mistake_anatomy",
        "glossary_card",
        "data_curiosity",
    )


def test_verticals_are_the_eight_agreed_lanes():
    assert VERTICALS == (
        "macro",
        "equities",
        "regulation",
        "earnings",
        "market_structure",
        "investing_concept",
        "personal_finance_concept",
        "practical_skills",
    )


def test_no_duplicates_in_either_set():
    assert len(set(ARCHETYPES)) == len(ARCHETYPES)
    assert len(set(VERTICALS)) == len(VERTICALS)


def test_tips_is_not_a_vertical():
    # Renamed to practical_skills on purpose: the vertical label reaches the
    # P2b drafting prompt, so a lane named "tips" would prime advisory register.
    assert "tips" not in VERTICALS
    assert "practical_skills" in VERTICALS


def test_membership_accepts_known_values():
    assert is_archetype("explainer")
    assert is_vertical("macro")


def test_membership_rejects_unknown_values():
    assert not is_archetype("top_5_funds")
    assert not is_vertical("stock_tips")


def test_membership_rejects_non_strings():
    assert not is_archetype(None)
    assert not is_archetype(3)
    assert not is_vertical(["macro"])
