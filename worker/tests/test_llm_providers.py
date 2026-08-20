import pytest

from app.llm.providers import PROVIDERS, ProviderError, available, is_retryable, _gemini_retryable


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


def test_available_treats_whitespace_only_key_as_absent(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
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


class MockGeminiError(Exception):
    """Mock google-genai SDK exception with .code attribute."""

    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


class MockGeminiErrorWithResponse(Exception):
    """Mock google-genai SDK exception with .response.status_code attribute."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.response = type("Response", (), {"status_code": status_code})()


def test_gemini_retryable_terminal_error_with_retryable_substring():
    """A terminal Gemini error (401) with a retryable-looking substring in the
    message (e.g., '503' in a request ID) must be classified terminal, not
    retried based on substring matching."""
    exc = MockGeminiError("request id: 503abc, api returned 401 Unauthorized", code=401)
    assert _gemini_retryable(exc) is False


def test_gemini_retryable_with_code_429():
    """HTTP 429 (Too Many Requests) must be classified retryable."""
    exc = MockGeminiError("rate limit exceeded", code=429)
    assert _gemini_retryable(exc) is True


def test_gemini_retryable_with_code_500():
    """HTTP 500 (server error) must be classified retryable."""
    exc = MockGeminiError("internal server error", code=500)
    assert _gemini_retryable(exc) is True


def test_gemini_retryable_with_code_403():
    """HTTP 403 (Forbidden) must be classified terminal."""
    exc = MockGeminiError("permission denied", code=403)
    assert _gemini_retryable(exc) is False


def test_gemini_retryable_with_response_status_code():
    """Extract status from .response.status_code when .code is not present."""
    exc = MockGeminiErrorWithResponse("forbidden", status_code=403)
    assert _gemini_retryable(exc) is False

    exc = MockGeminiErrorWithResponse("service unavailable", status_code=503)
    assert _gemini_retryable(exc) is True


def test_gemini_retryable_with_no_status():
    """Return None when no status code is present, allowing fallback to substring matching."""
    exc = RuntimeError("some generic error")
    assert _gemini_retryable(exc) is None
