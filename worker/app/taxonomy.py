"""Closed vocabularies for story classification (blueprint Part I §5).

These are code constants, not config, for the same reason the compliance
blocklist is (decisions #43, #44): in the config table they would be one GUI
edit away from removal, with no trace in git history. Adding a value is a
deliberate code change under owner approval, per §5.

The closure is the point. §2.2's listicle trap is defended structurally: the
model picks from a fixed set and an out-of-set answer is a validation failure,
so it cannot invent "top 5 funds" at 3 a.m.
"""

from __future__ import annotations

ARCHETYPES: tuple[str, ...] = (
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

# Topical lanes. Deliberately orthogonal to `market` (US/IN), which lives on
# `sources` and `items`. `practical_skills` covers how-to know-how (reading a
# cash-flow statement, driving a screener) and is NOT named `tips`: the label
# is injected into the P2b drafting prompt, so the word itself is a compliance
# surface.
VERTICALS: tuple[str, ...] = (
    "macro",
    "equities",
    "regulation",
    "earnings",
    "market_structure",
    "investing_concept",
    "personal_finance_concept",
    "practical_skills",
)


def is_archetype(value: object) -> bool:
    return isinstance(value, str) and value in ARCHETYPES


def is_vertical(value: object) -> bool:
    return isinstance(value, str) and value in VERTICALS
