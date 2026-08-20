import pytest

from app.llm.providers import PROVIDERS, ProviderError, available, is_retryable


def test_the_three_real_providers_are_registered():
    # No Anthropic and no Moonshot: this deployment has no key for either, so
    # the blueprint's §8 table names models that cannot be called here.
    assert set(PROVIDERS) == {"gemini", "deepseek", "openai"}


def test_every_provider_declares_its_env_key():
    assert PROVIDERS["gemini"].env_key == "GEMINI_API_KEY"
    assert PROVIDERS["deepseek"].env_key == "DEEPSEEK_API_KEY"
    assert PROVIDERS["openai"].env_key == "OPENAI_API_KEY"


def test_available_lists_only_providers_with_a_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert available() == ("gemini",)


def test_available_treats_an_empty_key_as_absent(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert available() == ()


def test_provider_error_carries_its_own_retryable_flag():
    assert is_retryable(ProviderError("boom", retryable=True))
    assert not is_retryable(ProviderError("bad key", retryable=False))


@pytest.mark.parametrize("message", ["429 Too Many Requests", "503 overloaded", "Read timed out"])
def test_transport_errors_are_classified_retryable(message):
    assert is_retryable(RuntimeError(message))


@pytest.mark.parametrize("message", ["401 Unauthorized", "400 Bad Request"])
def test_auth_and_shape_errors_are_not_retryable(message):
    assert not is_retryable(RuntimeError(message))
