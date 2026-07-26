"""Gemma via Google's generative-language API.

Used for development and for the reproducible eval, where a 77-second local vision
call would make iteration impossible. Not what the shipped watcher uses — see
`ollama.py` — because frames sent to a hosted endpoint leave the student's machine,
and `is_local` stays False here precisely so the UI cannot claim otherwise.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from .base import CallMeta, Provider, ProviderError, encode_image

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"


class GoogleProvider(Provider):
    supports_json_mode = True

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        timeout: float = 180.0,
        endpoint: str = ENDPOINT,
    ) -> None:
        super().__init__(model, timeout=timeout)
        self.api_key = api_key or os.environ.get("GEMMA_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        if not self.api_key:
            raise ProviderError("No API key: set GEMMA_API_KEY (or GOOGLE_API_KEY)")
        self.endpoint = endpoint.rstrip("/")
        # Gemma models on this API do not all accept the same generationConfig as
        # the Gemini models do. Rather than hard-code an assumption, we try the
        # richer request once and remember if the server rejects it.
        self._json_mode_supported = True

    @property
    def name(self) -> str:
        return "google"

    def list_models(self) -> list[str]:
        """Model handles this key can actually reach.

        Worth calling before anything else: the participant-guide handle, the
        Ollama tag and the API handle for the same weights are all different
        strings, and guessing wastes more time than asking.
        """
        response = requests.get(
            f"{self.endpoint}/models",
            headers={"x-goog-api-key": self.api_key},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise ProviderError(f"list_models failed [{response.status_code}]: {response.text[:300]}")
        payload = response.json()
        return [entry.get("name", "").removeprefix("models/") for entry in payload.get("models", [])]

    def generate(
        self,
        prompt: str,
        *,
        image: Any = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if image is not None:
            encoded, mime = encode_image(image)
            parts.append({"inline_data": {"mime_type": mime, "data": encoded}})

        config: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens}
        want_json = json_mode and self._json_mode_supported
        if want_json:
            config["responseMimeType"] = "application/json"

        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": config}
        url = f"{self.endpoint}/models/{self.model}:generateContent"

        try:
            response = requests.post(
                url,
                json=body,
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"request failed: {exc}") from exc

        if response.status_code == 400 and want_json and "response_mime_type" in response.text.lower():
            # This model doesn't do native JSON. Fall back permanently and let
            # the base class's prompt instruction plus brace scanner carry it.
            self._json_mode_supported = False
            return self.generate(
                prompt, image=image, max_tokens=max_tokens, temperature=temperature, json_mode=False
            )

        if response.status_code != 200:
            raise ProviderError(f"[{response.status_code}] {response.text[:400]}")

        return self._first_text(response.json())

    @staticmethod
    def _first_text(payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            blocked = payload.get("promptFeedback", {}).get("blockReason")
            raise ProviderError(f"no candidates returned{f' (blocked: {blocked})' if blocked else ''}")
        candidate = candidates[0]
        chunks = [
            part["text"]
            for part in candidate.get("content", {}).get("parts", [])
            if isinstance(part.get("text"), str)
        ]
        if not chunks:
            reason = candidate.get("finishReason", "unknown")
            raise ProviderError(f"empty response (finishReason={reason})")
        return "".join(chunks)
