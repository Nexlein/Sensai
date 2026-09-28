import pytest

from sensai.domain.errors import ProviderError
from sensai.providers import get_provider
from sensai.providers.mock import MockLLMProvider
from sensai.providers.ollama import OllamaLLMProvider


def test_get_provider_ollama_returns_configured_instance():
    provider = get_provider("ollama", base_url="http://example:1234", model="llama3.2")
    assert isinstance(provider, OllamaLLMProvider)
    assert provider.base_url == "http://example:1234"
    assert provider.model == "llama3.2"


def test_get_provider_mock_returns_configured_instance():
    provider = get_provider("mock", default_response="hi", simulated_delay=0)
    assert isinstance(provider, MockLLMProvider)
    assert provider.default_response == "hi"
    assert provider.simulated_delay == 0


def test_get_provider_unknown_name_raises_provider_error():
    with pytest.raises(ProviderError):
        get_provider("nonexistent")
