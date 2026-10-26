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


# Contract: every registered provider can stand in for another in ChatEngine.

PROVIDER_CONFIGS = {
    "ollama": {"model": "m"},
    "groq": {"model": "m", "api_key": "k"},
    "mock": {},
}


def test_every_registered_provider_has_a_contract_case():
    from sensai.providers import _REGISTRY

    assert set(_REGISTRY) == set(PROVIDER_CONFIGS)


@pytest.mark.parametrize("name", sorted(PROVIDER_CONFIGS))
def test_provider_chat_stream_matches_the_protocol(name):
    import inspect

    provider = get_provider(name, **PROVIDER_CONFIGS[name])
    signature = inspect.signature(provider.chat_stream)

    assert inspect.isasyncgenfunction(provider.chat_stream)
    assert list(signature.parameters)[:3] == ["messages", "tools", "think"]
    assert signature.parameters["tools"].default is None
    assert signature.parameters["think"].default is None


@pytest.mark.parametrize(
    ("name", "inspects"), [("ollama", True), ("groq", False), ("mock", False)]
)
def test_only_ollama_reports_loaded_models(name, inspects):
    from sensai.domain.protocols import ModelInspector

    provider = get_provider(name, **PROVIDER_CONFIGS[name])

    assert isinstance(provider, ModelInspector) is inspects
