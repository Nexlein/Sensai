import pytest

from sensai.domain.errors import ProviderError
from sensai.providers import get_provider
from sensai.providers.groq import GroqLLMProvider
from sensai.providers.mock import MockLLMProvider
from sensai.providers.ollama import OllamaLLMProvider


def test_get_provider_ollama_returns_configured_instance():
    provider = get_provider("ollama", base_url="http://example:1234", model="llama3.2")
    assert isinstance(provider, OllamaLLMProvider)
    assert provider.base_url == "http://example:1234"
    assert provider.model == "llama3.2"


def test_get_provider_groq_ignores_ollama_base_url():
    provider = get_provider(
        "groq", base_url="http://localhost:11434", model="m", api_key="k"
    )
    assert isinstance(provider, GroqLLMProvider)
    assert provider.model == "m"
    assert provider.base_url == "https://api.groq.com/openai/v1"


def test_get_provider_groq_without_key_raises_provider_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ProviderError):
        get_provider("groq")


def test_get_provider_mock_returns_configured_instance():
    provider = get_provider("mock", default_response="hi", simulated_delay=0)
    assert isinstance(provider, MockLLMProvider)
    assert provider.default_response == "hi"
    assert provider.simulated_delay == 0


def test_get_provider_unknown_name_raises_provider_error():
    with pytest.raises(ProviderError):
        get_provider("nonexistent")
