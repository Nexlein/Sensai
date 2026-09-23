from typing import Any

from sensai.domain.errors import ProviderError
from sensai.domain.protocols import LLMProvider
from sensai.providers.mock import MockLLMProvider
from sensai.providers.ollama import OllamaLLMProvider

_REGISTRY: dict[str, type[LLMProvider]] = {
    "ollama": OllamaLLMProvider,
    "mock": MockLLMProvider,
}


def get_provider(name: str, **cfg: Any) -> LLMProvider:
    try:
        provider_cls = _REGISTRY[name]
    except KeyError:
        raise ProviderError(
            f"Unknown provider '{name}'. Available providers: {sorted(_REGISTRY)}"
        ) from None
    return provider_cls(**cfg)
