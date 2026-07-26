"""Backend selection. One function decides where the weights run."""

from __future__ import annotations

from ..config import Settings, settings as default_settings
from .base import CallMeta, Provider, ProviderError, encode_image, extract_json
from .google_api import GoogleProvider
from .mock import MockProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider

__all__ = [
    "CallMeta",
    "GoogleProvider",
    "MockProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "Provider",
    "ProviderError",
    "encode_image",
    "extract_json",
    "get_provider",
]

#: Fallback handles used when HEIDDOON_MODEL is unset. These are guesses, and a
#: wrong guess is cheap to fix: every provider exposes `list_models()`, and the
#: CLI's `doctor` command prints what the configured key can actually reach.
DEFAULT_MODELS = {
    "google": "gemma-3-27b-it",
    #"openai_compat": "google/gemma-3-27b-it",
    "ollama": "gemma4:12b",
    "mock": "mock",
}


def get_provider(settings: Settings | None = None, *, provider: str | None = None) -> Provider:
    """Build the configured provider.

    Raises ProviderError with a readable message rather than returning a mock, so
    a misconfiguration is impossible to mistake for a working system.
    """
    config = settings or default_settings
    name = (provider or config.provider).strip().lower()
    model = config.model or DEFAULT_MODELS.get(name, "")

    if name == "google":
        return GoogleProvider(model, api_key=config.api_key, timeout=config.timeout_s)
    if name in ("openai_compat", "openai", "openrouter", "together", "groq", "fireworks"):
        base_url = config.base_url or (name if name != "openai_compat" else "")
        if not base_url:
            raise ProviderError(
                "openai_compat needs a base URL: set HEIDDOON_BASE_URL "
                "(or use HEIDDOON_PROVIDER=openrouter/together/groq/fireworks)"
            )
        return OpenAICompatProvider(model, base_url=base_url, api_key=config.api_key, timeout=config.timeout_s)
    if name == "ollama":
        return OllamaProvider(
            config.model or config.ollama_model, host=config.ollama_host, timeout=max(config.timeout_s, 300.0)
        )
    if name == "mock":
        return MockProvider()

    raise ProviderError(f"unknown provider {name!r}; expected one of: google, openai_compat, ollama, mock")
