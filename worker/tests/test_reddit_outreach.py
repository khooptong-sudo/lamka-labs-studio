"""Outreach: approval-gated sends under caps. PRAW always faked."""

from unittest.mock import AsyncMock, Mock, patch

import pytest


PM_TEMPLATE = (
    "Hi u/{author} — I run an educational YouTube channel and your post "
    "\"{title}\" (r/{sub}) would make a strong segment. May I adapt it into "
    "a narrated video with full on-screen credit to you and a link to your "
    "post? Reply YES and I'll send you the link when it's live, or NO and "
    "I'll never ask again. — Min"
)


def _pm_row(**over):
    row = {
        "post_url": "https://www.reddit.com/r/x/comments/p1/",
        "author": "sleuth",
        "subreddit": "UnresolvedMysteries",
        "title": "The case",
        "state": "pm_approved",
        "pm_text": "hi",
    }
    row.update(over)
    return row


def test_pm_template_verbatim():
    from app import reddit_outreach

    assert reddit_outreach.PM_TEMPLATE == PM_TEMPLATE


async def test_send_refuses_without_approval():
    from app import reddit_outreach

    with pytest.raises(reddit_outreach.OutreachError, match="pm_approved"):
        await reddit_outreach.send_pm(
            sender=object(), post_url="https://r/x/a", author="s",
            subreddit="S", title="T", state="candidate", pm_text="hi",
            dry_run=False,
        )


async def test_send_caps_per_day():
    from app import reddit_outreach

    sent = []

    class FakeMessage:
        pass

    class FakeRedditor:
        def __init__(self, name):
            self.name = name

        def message(self, subject, body):
            sent.append((subject, body))
            return FakeMessage()

    class FakeSender:
        def redditor(self, name):
            return FakeRedditor(name)

    message_id = await reddit_outreach.send_pm(
        sender=FakeSender(), post_url="https://r/x/a", author="s",
        subreddit="S", title="T", state="pm_approved", pm_text="hi",
        dry_run=False,
    )
    assert message_id is not None
    assert sent[0][1] == "hi"  # exact approved text, never reworded


async def test_sender_job_respects_daily_cap(monkeypatch):
    """sent_today >= 5 → skip with log, no API call (no sender build, no send)."""
    from app import reddit_outreach

    monkeypatch.setenv("REDDIT_OUTREACH_LIVE", "true")
    monkeypatch.setattr(reddit_outreach, "_sent_today_count", AsyncMock(return_value=5))
    monkeypatch.setattr(reddit_outreach, "_approved_queue", AsyncMock(return_value=[_pm_row()]))
    send = AsyncMock()
    monkeypatch.setattr(reddit_outreach, "send_pm", send)
    build = Mock()
    monkeypatch.setattr(reddit_outreach, "_build_sender", build)

    summary = await reddit_outreach.reddit_outreach_job()

    assert summary["sent"] == 0
    assert summary["skipped"] == "daily_cap"
    send.assert_not_awaited()
    build.assert_not_called()


async def test_sender_job_dry_run_logs_without_sending(monkeypatch):
    """Kill switch off (default) → log the exact PM, leave state, touch nothing."""
    from app import reddit_outreach

    monkeypatch.delenv("REDDIT_OUTREACH_LIVE", raising=False)
    monkeypatch.setattr(reddit_outreach, "_sent_today_count", AsyncMock(return_value=0))
    monkeypatch.setattr(reddit_outreach, "_approved_queue", AsyncMock(return_value=[_pm_row()]))
    send = AsyncMock()
    mark = AsyncMock()
    build = Mock()
    monkeypatch.setattr(reddit_outreach, "send_pm", send)
    monkeypatch.setattr(reddit_outreach, "_mark_sent", mark)
    monkeypatch.setattr(reddit_outreach, "_build_sender", build)

    summary = await reddit_outreach.reddit_outreach_job()

    assert summary["dry_run"] is True
    assert summary["sent"] == 0
    assert summary["skipped"] == "dry_run"
    send.assert_not_awaited()
    mark.assert_not_awaited()
    build.assert_not_called()


async def test_sender_job_sends_when_live_under_cap(monkeypatch):
    from app import reddit_outreach

    monkeypatch.setenv("REDDIT_OUTREACH_LIVE", "true")
    monkeypatch.setattr(reddit_outreach, "_sent_today_count", AsyncMock(return_value=0))
    monkeypatch.setattr(reddit_outreach, "_approved_queue", AsyncMock(return_value=[_pm_row()]))
    monkeypatch.setattr(reddit_outreach, "_build_sender", Mock(return_value=object()))
    monkeypatch.setattr(reddit_outreach, "send_pm", AsyncMock(return_value="msg-1"))
    mark = AsyncMock()
    sweep = AsyncMock(return_value=0)
    monkeypatch.setattr(reddit_outreach, "_mark_sent", mark)
    monkeypatch.setattr(reddit_outreach, "_sweep_inbox", sweep)

    summary = await reddit_outreach.reddit_outreach_job()

    assert summary["sent"] == 1
    assert summary["dry_run"] is False
    mark.assert_awaited_once_with("https://www.reddit.com/r/x/comments/p1/", "msg-1")
    sweep.assert_awaited_once()


async def test_sweep_flips_sent_rows_to_review_then_marks_read(monkeypatch):
    """Inbox sweep: a reply from an author with a sent row → review. The
    message is marked read only after the flip is recorded."""
    from app import reddit_outreach

    events = []

    class FakeAuthor:
        def __init__(self, name):
            self.name = name

    class FakeMsg:
        def __init__(self, author):
            self.author = FakeAuthor(author)

        def mark_read(self):
            events.append(("read", self.author.name))

    inbox = Mock()
    inbox.unread.return_value = [FakeMsg("sleuth"), FakeMsg("stranger")]
    sender = Mock()
    sender.inbox = inbox

    async def fake_urls(author):
        return ["https://r/x/p1"] if author == "sleuth" else []

    async def fake_review(url):
        events.append(("review", url))

    monkeypatch.setattr(reddit_outreach, "_sent_urls_for_author", fake_urls)
    monkeypatch.setattr(reddit_outreach, "_mark_review", fake_review)

    flipped = await reddit_outreach._sweep_inbox(sender)

    assert flipped == 1
    assert events[0] == ("review", "https://r/x/p1")
    assert ("read", "sleuth") in events
    assert ("read", "stranger") in events
    assert events.index(("review", "https://r/x/p1")) < events.index(("read", "sleuth"))


def test_approve_validator_refuses_opted_out_author():
    """Denied opts the author out forever: their posts stay candidate."""
    from app import reddit_outreach

    with pytest.raises(reddit_outreach.OutreachError, match="opted out"):
        reddit_outreach.validate_approve(
            {"post_url": "https://r/x/a", "author": "s", "state": "candidate"},
            pm_text="hi",
            opted_out=True,
        )


def test_approve_validator_requires_nonempty_text():
    from app import reddit_outreach

    with pytest.raises(reddit_outreach.OutreachError, match="non-empty"):
        reddit_outreach.validate_approve(
            {"post_url": "https://r/x/a", "author": "s", "state": "candidate"},
            pm_text="   ",
            opted_out=False,
        )


def test_approve_validator_requires_candidate_state():
    from app import reddit_outreach

    with pytest.raises(reddit_outreach.OutreachError, match="pm_approved"):
        reddit_outreach.validate_approve(
            {"post_url": "https://r/x/a", "author": "s", "state": "sent"},
            pm_text="hi",
            opted_out=False,
        )


def test_decide_validator_moves_review_to_granted_or_denied():
    from app import reddit_outreach

    row = {"post_url": "https://r/x/a", "author": "s", "state": "review"}
    assert reddit_outreach.validate_decide(row, "granted") == "granted"
    assert reddit_outreach.validate_decide(row, "denied") == "denied"


def test_decide_validator_rejects_non_review_state():
    from app import reddit_outreach

    with pytest.raises(reddit_outreach.OutreachError):
        reddit_outreach.validate_decide(
            {"post_url": "https://r/x/a", "author": "s", "state": "candidate"},
            "granted",
        )


def test_reddit_rights_route_lists_by_state():
    from fastapi.testclient import TestClient

    from app.main import app

    with patch("app.reddit_outreach.list_rights", AsyncMock(return_value=[])) as lst:
        resp = TestClient(app).get("/reddit/rights", params={"state": "candidate"})
    assert resp.status_code == 200
    lst.assert_awaited_once_with("candidate")


def test_reddit_approve_route_approves_and_maps_missing_to_404():
    from fastapi.testclient import TestClient

    from app import reddit_outreach
    from app.main import app

    client = TestClient(app)
    with patch(
        "app.reddit_outreach.approve_right",
        AsyncMock(return_value=_pm_row(state="pm_approved")),
    ):
        resp = client.post("/reddit/approve", json={"post_url": "https://r/x/a", "pm_text": "hi"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "pm_approved"

    with patch(
        "app.reddit_outreach.approve_right",
        AsyncMock(side_effect=reddit_outreach.NotFoundError("no reddit right")),
    ):
        resp = client.post("/reddit/approve", json={"post_url": "https://r/x/a", "pm_text": "hi"})
    assert resp.status_code == 404


def test_reddit_decide_route_decides_from_review():
    from fastapi.testclient import TestClient

    from app.main import app

    with patch(
        "app.reddit_outreach.decide_right",
        AsyncMock(return_value=_pm_row(state="granted")),
    ) as decide:
        resp = TestClient(app).post(
            "/reddit/decide", json={"post_url": "https://r/x/a", "verdict": "granted"}
        )
    assert resp.status_code == 200
    assert resp.json()["state"] == "granted"
    decide.assert_awaited_once_with(post_url="https://r/x/a", verdict="granted")
