"""Gemma behind any OpenAI-shaped chat-completions endpoint.

One class covers OpenRouter, Together, Groq, Fireworks, a self-hosted vLLM and
Ollama's compatibility route, because they all speak the same wire format. Which
of them holds the key matters to billing and latency, not to this codebase.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from .base import Provider, ProviderError, encode_image

KNOWN_BASES = {
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "groq": "https://api.groq.com/openai/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "local": "http://localhost:11434/v1",
}


class OpenAICompatProvider(Provider):
    supports_json_mode = True

    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(model, timeout=timeout)
        self.base_url = KNOWN_BASES.get(base_url, base_url).rstrip("/")
        self.api_key = api_key or os.environ.get("GEMMA_API_KEY", "")
        self._json_mode_supported = True

    @property
    def name(self) -> str:
        return "openai_compat"

    @property
    def is_local(self) -> bool:
        return "localhost" in self.base_url or "127.0.0.1" in self.base_url

    def list_models(self) -> list[str]:
        response = requests.get(f"{self.base_url}/models", headers=self._headers(), timeout=self.timeout)
        if response.status_code != 200:
            raise ProviderError(f"list_models failed [{response.status_code}]: {response.text[:300]}")
        return [entry.get("id", "") for entry in response.json().get("data", [])]

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate(
        self,
        prompt: str,
        *,
        image: Any = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image is not None:
            encoded, mime = encode_image(image)
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})

        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        want_json = json_mode and self._json_mode_supported
        if want_json:
            body["response_format"] = {"type": "json_object"}

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"request failed: {exc}") from exc

        if response.status_code == 400 and want_json and "response_format" in response.text.lower():
            self._json_mode_supported = False
            return self.generate(
                prompt, image=image, max_tokens=max_tokens, temperature=temperature, json_mode=False
            )

        if response.status_code != 200:
            raise ProviderError(f"[{response.status_code}] {response.text[:400]}")

        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise ProviderError(f"no choices returned: {str(payload)[:300]}")
        message = choices[0].get("message", {})
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise ProviderError(f"empty content (finish_reason={choices[0].get('finish_reason')})")
        return text
