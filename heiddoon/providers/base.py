"""Provider interface — one seam between the product and where the weights run.

Heid Doon's ethical claim depends on the shipped watcher running the model on the
student's own machine. Its development speed depends on a hosted endpoint. Both are
true at once only if there is exactly one place in the codebase that knows the
difference, and this is it: every mechanic calls `complete_json` and cannot tell
which backend answered.
"""

from __future__ import annotations

import base64
import io
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

try:  # Pillow is required for image frames but not for text-only mechanics.
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]


class ProviderError(RuntimeError):
    """The backend could not be reached or refused the request."""


@dataclass
class CallMeta:
    """What it cost and whether we had to fight for it. Surfaced in the eval."""

    provider: str
    model: str
    latency_s: float
    attempts: int
    ok: bool
    raw: str = ""
    error: str = ""
    had_image: bool = False
    repairs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "latency_s": round(self.latency_s, 2),
            "attempts": self.attempts,
            "ok": self.ok,
            "error": self.error,
            "had_image": self.had_image,
            "repairs": self.repairs,
        }


def encode_image(image: Any, max_size: tuple[int, int] = (1024, 640), quality: int = 70) -> tuple[str, str]:
    """Frame → (base64 JPEG, mime type).

    Downscaling is not only bandwidth: a 4K screenshot fed to a vision model at
    full resolution costs a large multiple of the tokens for no accuracy gain on
    "what am I looking at". 1024×640 keeps window titles and headings legible,
    which is what the verdict actually turns on.
    """
    if Image is None:  # pragma: no cover
        raise ProviderError("Pillow is required to send image frames: pip install pillow")
    if isinstance(image, (bytes, bytearray)):
        return base64.b64encode(bytes(image)).decode(), "image/jpeg"

    frame = image.copy() if hasattr(image, "copy") else image
    if frame.mode != "RGB":
        frame = frame.convert("RGB")
    frame.thumbnail(max_size)
    buffer = io.BytesIO()
    frame.save(buffer, "JPEG", quality=quality)
    return base64.b64encode(buffer.getvalue()).decode(), "image/jpeg"


def extract_json(text: str) -> dict[str, Any] | None:
    """Pull the first complete JSON object out of a model response.

    Deliberately a brace-matching scanner rather than a regex. The obvious
    `\\{.*\\}` spans from the first brace to the *last* one in the string, so any
    trailing commentary containing a brace — or a second object — corrupts the
    parse. Small models emit both often enough to matter.
    """
    if not text:
        return None

    # Strip a fenced block if present; the fence content is usually the whole payload.
    fenced = text.strip()
    if fenced.startswith("```"):
        newline = fenced.find("\n")
        if newline != -1:
            closing = fenced.rfind("```")
            fenced = fenced[newline + 1 : closing if closing > newline else len(fenced)]

    for source in (fenced, text):
        depth = 0
        start = -1
        in_string = False
        escaped = False
        for index, char in enumerate(source):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                if depth == 0:
                    start = index
                depth += 1
            elif char == "}":
                if depth:
                    depth -= 1
                    if depth == 0 and start != -1:
                        try:
                            parsed = json.loads(source[start : index + 1])
                        except json.JSONDecodeError:
                            start = -1
                            continue
                        if isinstance(parsed, dict):
                            return parsed
                        start = -1
    return None


class Provider(ABC):
    """A place where Gemma runs. Subclasses implement `generate` only."""

    #: Set by subclasses that can be asked for JSON at the API level rather than
    #: by pleading in the prompt. Native mode removes most parse failures.
    supports_json_mode = False

    def __init__(self, model: str, *, timeout: float = 180.0) -> None:
        self.model = model
        self.timeout = timeout

    @property
    def name(self) -> str:
        return type(self).__name__.replace("Provider", "").lower()

    @property
    def is_local(self) -> bool:
        """Whether frames stay on this machine. Drives what the UI may claim."""
        return False

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        image: Any = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        """Return the model's raw text for one prompt (plus optional frame)."""

    def complete_json(
        self,
        prompt: str,
        *,
        image: Any = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
        attempts: int = 3,
    ) -> tuple[dict[str, Any], CallMeta]:
        """The only call the rest of the product makes.

        Returns `({}, meta)` with `meta.ok == False` when every attempt failed,
        so callers can degrade rather than raise mid-session.
        """
        started = time.time()
        last_raw = ""
        last_error = ""
        instruction = "\nReply with ONLY one JSON object and no other text."

        for attempt in range(1, attempts + 1):
            try:
                last_raw = self.generate(
                    prompt if self.supports_json_mode else prompt + instruction,
                    image=image,
                    max_tokens=max_tokens,
                    # Nudge temperature up slightly on retry: a model that has
                    # produced unparseable output once at t=0.2 will usually
                    # reproduce it verbatim, so a literal retry is wasted.
                    temperature=temperature if attempt == 1 else min(0.9, temperature + 0.2 * attempt),
                    json_mode=self.supports_json_mode,
                )
            except ProviderError as exc:
                last_error = str(exc)
                continue

            parsed = extract_json(last_raw)
            if parsed is not None:
                return parsed, CallMeta(
                    provider=self.name,
                    model=self.model,
                    latency_s=time.time() - started,
                    attempts=attempt,
                    ok=True,
                    raw=last_raw,
                    had_image=image is not None,
                )
            last_error = "no JSON object in response"

        return {}, CallMeta(
            provider=self.name,
            model=self.model,
            latency_s=time.time() - started,
            attempts=attempts,
            ok=False,
            raw=last_raw[:800],
            error=last_error,
            had_image=image is not None,
        )
