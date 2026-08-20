"""The router is the seam every test patches (recorded bug #13). These tests
are the only place a fake 'provider' exists; nothing here touches the network."""

import pytest

from app.llm import contract, providers, router

SPEC = contract.FieldSpec(validators={"verdict": lambda v: v in ("yes", "no")})

ROUTE = {"demo": {"primary": "gemini", "fallback": "deepseek"}}


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    """Retry timing is not what these tests are about, and a real backoff would
    make the exhaustion test take 20 seconds."""
    monkeypatch.setattr(router, "_backoff", lambda _attempt: 0)


@pytest.fixture
def routed(monkeypatch):
    """Route 'demo' at gemini->deepseek, with both keys present."""
    async def _cfg():
        from app.config import LLMConfig

        return LLMConfig(routing=ROUTE)

    monkeypatch.setattr(router, "get_llm_config", _cfg)
    monkeypatch.setattr(providers, "available", lambda: ("gemini", "deepseek", "openai"))


def _provider_returning(*replies):
    """A fake provider whose successive calls return the given replies.

    A reply that is an Exception instance is raised instead of returned.
    """
    calls: list[str] = []

    async def _call(system: str, user: str) -> str:
        calls.append(user)
        reply = replies[min(len(calls) - 1, len(replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply

    _call.calls = calls  # type: ignore[attr-defined]
    return _call


async def test_returns_the_validated_payload(routed, monkeypatch):
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", _provider_returning('{"verdict": "yes"}')),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC)
    assert result == {"verdict": "yes"}


async def test_retries_a_retryable_error_on_the_same_provider(routed, monkeypatch):
    call = _provider_returning(RuntimeError("429 rate limited"), '{"verdict": "no"}')
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", call),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC)
    assert result == {"verdict": "no"}
    assert len(call.calls) == 2


async def test_falls_straight_through_to_the_fallback_on_a_terminal_error(routed, monkeypatch):
    primary = _provider_returning(RuntimeError("401 Unauthorized"))
    fallback = _provider_returning('{"verdict": "yes"}')
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", primary),
    )
    monkeypatch.setitem(
        providers.PROVIDERS, "deepseek",
        providers.Provider("deepseek", "DEEPSEEK_API_KEY", fallback),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC)
    assert result == {"verdict": "yes"}
    # Terminal means no retry against the primary at all.
    assert len(primary.calls) == 1


async def test_repairs_an_invalid_payload_exactly_once(routed, monkeypatch):
    call = _provider_returning('{"verdict": "maybe"}', '{"verdict": "yes"}')
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", call),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC)
    assert result == {"verdict": "yes"}
    assert len(call.calls) == 2
    # The repair prompt tells the model what was wrong.
    assert "maybe" in call.calls[1]


async def test_gives_up_after_one_failed_repair(routed, monkeypatch):
    always_bad = _provider_returning('{"verdict": "maybe"}')
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", always_bad),
    )
    monkeypatch.setitem(
        providers.PROVIDERS, "deepseek",
        providers.Provider("deepseek", "DEEPSEEK_API_KEY", _provider_returning('{"verdict": "no"}')),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC)
    assert result == {"verdict": "no"}
    # Original attempt plus one repair, then hand off. Never an endless loop.
    assert len(always_bad.calls) == 2


async def test_raises_when_every_provider_is_exhausted(routed, monkeypatch):
    for name, env in (("gemini", "GEMINI_API_KEY"), ("deepseek", "DEEPSEEK_API_KEY")):
        monkeypatch.setitem(
            providers.PROVIDERS, name,
            providers.Provider(name, env, _provider_returning(RuntimeError("503 down"))),
        )
    with pytest.raises(router.RouterError, match="exhausted"):
        await router.complete_json("demo", system="s", user="u", spec=SPEC)


async def test_raises_when_the_task_has_no_route(routed):
    with pytest.raises(router.RouterError, match="no available provider"):
        await router.complete_json("unrouted", system="s", user="u", spec=SPEC)


async def test_skips_a_routed_provider_whose_key_is_absent(monkeypatch):
    async def _cfg():
        from app.config import LLMConfig

        return LLMConfig(routing=ROUTE)

    monkeypatch.setattr(router, "get_llm_config", _cfg)
    # Primary is routed but has no key; only the fallback is usable.
    monkeypatch.setattr(providers, "available", lambda: ("deepseek",))
    fallback = _provider_returning('{"verdict": "yes"}')
    monkeypatch.setitem(
        providers.PROVIDERS, "deepseek",
        providers.Provider("deepseek", "DEEPSEEK_API_KEY", fallback),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC)
    assert result == {"verdict": "yes"}
    assert len(fallback.calls) == 1


async def test_never_returns_a_default(routed, monkeypatch):
    """Decision #41 generalized: there is no fabricated-result path."""
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", _provider_returning("not json at all")),
    )
    monkeypatch.setitem(
        providers.PROVIDERS, "deepseek",
        providers.Provider("deepseek", "DEEPSEEK_API_KEY", _provider_returning("also not json")),
    )
    with pytest.raises(router.RouterError):
        await router.complete_json("demo", system="s", user="u", spec=SPEC)
