"""Documentary acts: pure planning math, no network, no LLMs."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels import Channel


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


DOC_FINANCE = Channel(
    id="financial-channel", display_name="Finance", voice_key="adult_male",
    script_prompt="Be sober.", extra_blocklist=(),
)


def _doc_act_board(start, n=7):
    scenes = "\n\n".join(
        f"# Scene {i} — Ch{i}\n"
        f"Voiceover: \"A sufficiently long narration line for scene {i} here.\"\n"
        f"Scene: art {i}."
        for i in range(start, start + n)
    )
    return f"---\ntitle: Doc\ndescription: D\npreset: adult_male\n---\n\n{scenes}"


def _doc_acts():
    from app import documentary

    return [
        documentary.ActPlan(title="A", hook="h", beats=["b"] * 7, sources=[0]),
        documentary.ActPlan(title="B", hook="h", beats=["b"] * 7, sources=[1]),
        documentary.ActPlan(title="C", hook="h", beats=["b"] * 7, sources=[2]),
    ]


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=DOC_FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story", AsyncMock(side_effect=AssertionError("shorts path must not run")))
@patch("app.youtube.fact_check_script")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube.build_thumbnail_variants")
@patch("app.youtube._research_packet", return_value="packet")
async def test_documentary_branch_aborts_when_an_act_fails(
    mock_packet, mock_thumb, mock_run, mock_frames, mock_audio, mock_fact, mock_record, mock_fetch, tmp_path, monkeypatch
):
    from app import documentary
    from app.youtube import generate_youtube_video

    monkeypatch.setattr(
        documentary, "plan_outline",
        AsyncMock(return_value=documentary.DocumentaryOutline(title="Doc", acts=_doc_acts())),
    )
    calls = {"n": 0}

    async def fake_act(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("act provider down")
        return _doc_act_board(1)

    monkeypatch.setattr(documentary, "generate_act", fake_act)
    mock_fetch.return_value = {"headline": "T", "items": [
        {"title": "T0", "url": "https://x/0", "source_name": "S", "published_at": None, "full_text": "body"},
    ]}
    mock_fact.return_value = {"verdict": "PASS", "violations": []}
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        assert await generate_youtube_video(
            story_id=uuid.uuid4(), channel_id="financial-channel",
            documentary=True, brief="owner notes",
        ) is None
    assert calls["n"] == 2
    mock_record.assert_not_called()


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=DOC_FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story", AsyncMock(side_effect=AssertionError("shorts path must not run")))
@patch("app.youtube.fact_check_script")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube.build_thumbnail_variants")
@patch("app.youtube._research_packet", return_value="packet")
async def test_documentary_happy_path_merges_and_records(
    mock_packet, mock_thumb, mock_run, mock_frames, mock_audio, mock_fact, mock_record, mock_fetch, tmp_path, monkeypatch
):
    from app import documentary
    from app.youtube import generate_youtube_video

    monkeypatch.setattr(
        documentary, "plan_outline",
        AsyncMock(return_value=documentary.DocumentaryOutline(title="Doc", acts=_doc_acts())),
    )
    boards = [_doc_act_board(1), _doc_act_board(8), _doc_act_board(15)]
    monkeypatch.setattr(
        documentary, "generate_act",
        AsyncMock(side_effect=list(boards)),
    )
    story_id = uuid.uuid4()
    mock_fetch.return_value = {"headline": "T", "items": [
        {"title": "T0", "url": "https://x/0", "source_name": "S", "published_at": None, "full_text": "body"},
    ]}
    mock_fact.return_value = {"verdict": "PASS", "violations": []}
    mock_audio.return_value = []
    mock_frames.return_value = []
    mock_thumb.return_value = {}
    mock_record.return_value = uuid.uuid4()
    mock_run.return_value = MagicMock(stdout="mocked")
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        draft_id = await generate_youtube_video(
            story_id=story_id, channel_id="financial-channel",
            documentary=True, brief="owner notes",
        )
    assert draft_id is not None
    assert mock_fact.await_count == 3
    board_text = (tmp_path / f"story-{story_id}" / "STORYBOARD.md").read_text(encoding="utf-8")
    assert board_text.count("# Scene") == 21
    assert board_text.count("---") == 2  # one frontmatter block


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=DOC_FINANCE))
@patch("app.youtube._fetch_story_details")
async def test_documentary_needs_evidence_or_brief(mock_fetch, tmp_path):
    from app.youtube import generate_youtube_video

    mock_fetch.return_value = {"headline": "T", "items": []}
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        assert await generate_youtube_video(
            story_id=uuid.uuid4(), channel_id="financial-channel", documentary=True,
        ) is None
