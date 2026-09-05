"""Documentary acts: pure planning math, no network, no LLMs."""

import pytest


def _items(n):
    return [{"title": f"T{i}", "url": f"https://x/{i}", "source_name": "S",
             "published_at": None, "excerpt": f"excerpt {i}"} for i in range(n)]


def test_deal_sources_splits_round_robin():
    from app.documentary import deal_sources

    dealt = deal_sources(_items(7), 3)
    assert [[it["title"] for it in act] for act in dealt] == [
        ["T0", "T3", "T6"], ["T1", "T4"], ["T2", "T5"],
    ]


def test_deal_sources_handles_fewer_items_than_acts():
    from app.documentary import deal_sources

    dealt = deal_sources(_items(2), 4)
    assert [len(act) for act in dealt] == [1, 1, 0, 0]


def test_validate_outline_accepts_a_good_plan():
    from app.documentary import validate_outline

    payload = {"title": "T", "acts": [
        {"title": f"A{i}", "hook": f"hook {i}",
         "beats": [f"beat {i}-{j}" for j in range(7)], "sources": [i]}
        for i in range(3)
    ]}
    assert validate_outline(payload, 10) == []


def test_validate_outline_rejects_bad_counts_and_indices():
    from app.documentary import validate_outline

    assert validate_outline({"title": "T", "acts": []}, 4)
    many = {"title": "T", "acts": [
        {"title": "A", "hook": "h", "beats": ["b"] * 7, "sources": []}
        for _ in range(5)
    ]}
    assert validate_outline(many, 4)
    bad_beats = {"title": "T", "acts": [
        {"title": "A", "hook": "h", "beats": ["b"] * 4, "sources": []}
        for _ in range(3)
    ]}
    assert validate_outline(bad_beats, 4)
    bad_idx = {"title": "T", "acts": [
        {"title": "A", "hook": "h", "beats": ["b"] * 7, "sources": [9]}
        for _ in range(3)
    ]}
    assert validate_outline(bad_idx, 4)


def test_validate_outline_rejects_missing_fields():
    from app.documentary import validate_outline

    assert validate_outline({"title": "T"}, 4)
    assert validate_outline({"title": "", "acts": [
        {"title": "A", "hook": "h", "beats": ["b"] * 7, "sources": []}
        for _ in range(3)
    ]}, 4)


async def test_plan_outline_parses_provider_json(monkeypatch):
    from app import documentary

    payload = {"title": "Doc", "acts": [
        {"title": "A", "hook": "h", "beats": ["b"] * 7, "sources": [0]}
    ] * 3}
    import json

    async def fake_call(system, user):
        assert "3-4 acts" in system
        return json.dumps(payload)

    monkeypatch.setitem(
        documentary.PROVIDERS, "gemini",
        documentary.Provider("gemini", "GEMINI_API_KEY", fake_call),
    )
    outline = await documentary.plan_outline(
        headline="Head", packet="packet", provider="gemini", n_sources=4
    )
    assert outline.title == "Doc"
    assert len(outline.acts) == 3


async def test_generate_act_sends_recap_and_bundle(monkeypatch):
    from app import documentary

    seen = {}

    async def fake_call(system, user):
        seen["system"] = system
        seen["user"] = user
        return "# Scene 1 — X\nVoiceover: \"A sufficiently long narration line here.\"\n"

    monkeypatch.setitem(
        documentary.PROVIDERS, "gemini",
        documentary.Provider("gemini", "GEMINI_API_KEY", fake_call),
    )
    act = documentary.ActPlan(title="A", hook="h", beats=["b"] * 7, sources=[0])
    await documentary.generate_act(
        act=act, act_index=1, n_acts=3, first_scene=8, recap="PREV CLOSE",
        bundle_text="SOURCE 1...", channel_prompt="Be sober.",
        provider="gemini", want_hook=False, want_closing=True,
    )
    assert "PREV CLOSE" in seen["user"]
    assert "SOURCE 1..." in seen["user"]
    assert "8..14" in seen["user"]
    assert "Be sober." in seen["system"]


def test_merge_keeps_first_frontmatter_and_direction_only():
    from app.documentary import merge_acts

    act1 = (
        "---\ntitle: Doc\ndescription: D\n---\n\n"
        "# Video direction\nA dark world.\n\n"
        "# Scene 1 — A\nVoiceover: \"A sufficiently long narration line here.\"\n"
    )
    act2 = (
        "---\ntitle: Other\ndescription: X\n---\n\n"
        "# Video direction\nA bright world.\n\n"
        "# Scene 1 — B\nVoiceover: \"Another sufficiently long narration line.\"\n"
    )
    merged = merge_acts([act1, act2])
    assert merged.count("---") == 2  # one frontmatter block
    assert "A dark world." in merged
    assert "A bright world." not in merged
    assert "# Scene 1 — A" in merged and "# Scene 1 — B" in merged


def test_merge_refuses_empty_input():
    from app.documentary import merge_acts

    with pytest.raises(ValueError):
        merge_acts([])


def test_last_voiceover_returns_the_final_line():
    from app.documentary import last_voiceover

    board = "# Scene 1 — A\nVoiceover: \"First line here.\"\n\n# Scene 2 — B\nVoiceover: \"Second line here.\"\n"
    assert last_voiceover(board) == "Second line here."
    assert last_voiceover("no scenes here") == ""
