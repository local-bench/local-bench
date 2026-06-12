from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from localbench.providers._anthropic import AnthropicProvider
from localbench.providers._base import Lane, Provider, ProviderName, ProviderPayloadError
from localbench.providers._openai import OpenAIChatProvider, OpenAIReasoningProvider

__all__ = [
    "Lane",
    "Provider",
    "ProviderName",
    "ProviderPayloadError",
    "provider_choices",
    "provider_for_name",
]


@dataclass(frozen=True, slots=True)
class UnknownProviderError(Exception):
    name: str

    def __str__(self) -> str:
        return f"unknown provider: {self.name}"


_PROVIDERS: Final[dict[str, Provider]] = {
    "local": OpenAIChatProvider(name="local"),
    "openai-chat": OpenAIChatProvider(),
    "openai-reasoning": OpenAIReasoningProvider(),
    "anthropic": AnthropicProvider(),
    "gemini": OpenAIChatProvider(name="gemini"),
}


def provider_choices() -> tuple[str, ...]:
    return tuple(_PROVIDERS)


def provider_for_name(name: str) -> Provider:
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise UnknownProviderError(name)
    return provider
