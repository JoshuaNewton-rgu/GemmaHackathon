"""Gemma on the student's own machine, via Ollama.

This is the backend the product ships with, and the only one for which the privacy
claim is true: frames are judged in-process and never sent anywhere. `is_local` is
True here and nowhere else.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from .base import Provider, ProviderError, encode_image

DEFAULT_HOST = "http://localhost:11434"


class OllamaProvider(Provider):
    supports_json_mode = True

    def __init__(self, model: str, *, host: str = DEFAULT_HOST, timeout: float = 300.0) -> None:
        # Local CPU inference on a machine without CUDA can take over a minute for
        # a single vision call, so the default timeout is far longer than the
        # hosted providers'. A timeout here is a slow laptop, not a failure.
        super().__init__(model, timeout=timeout)
        self.host = host.rstrip("/")

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def is_local(self) -> bool:
        return True

    def list_models(self) -> list[str]:
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=10)
        except requests.RequestException as exc:
            raise ProviderError(f"Ollama unreachable at {self.host}: {exc}") from exc
        if response.status_code != 200:
            raise ProviderError(f"list_models failed [{response.status_code}]")
        return [entry.get("name", "") for entry in response.json().get("models", [])]

    def generate(
        self,
        prompt: str,
        *,
        image: Any = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"
        if image is not None:
            encoded, _ = encode_image(image)
            body["images"] = [encoded]

        try:
            response = requests.post(f"{self.host}/api/generate", json=body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ProviderError(f"Ollama unreachable at {self.host}: {exc}") from exc

        if response.status_code != 200:
            raise ProviderError(self._explain(response.text, response.status_code))

        try:
            return response.json().get("response", "")
        except json.JSONDecodeError as exc:
            raise ProviderError(f"malformed Ollama response: {exc}") from exc

    def _explain(self, body: str, status: int) -> str:
        """Turn Ollama's runtime crashes into something actionable.

        A model whose weights loaded fine can still abort on every call when the
        backend and the hardware disagree — observed on Intel Arc with the E4B
        vision tag, which dies with a GGML scheduler assertion rather than an
        out-of-memory error. Without this hint the failure reads as a bug in
        Heid Doon, and the obvious fix (a different tag, or the API backend) isn't
        suggested anywhere.
        """
        lowered = body.lower()
        if "ggml_assert" in lowered or "has terminated" in lowered:
            return (
                f"[{status}] the Ollama runtime crashed serving {self.model!r}. This usually means the "
                f"model/hardware combination is unsupported rather than out of memory. Try a smaller or "
                f"differently-quantised tag, or run with HEIDDOON_PROVIDER=google for now.\n"
                f"Ollama said: {body[:300]}"
            )
        if "not found" in lowered:
            return f"[{status}] model {self.model!r} is not pulled. Run: ollama pull {self.model}\n{body[:200]}"
        return f"[{status}] {body[:400]}"
