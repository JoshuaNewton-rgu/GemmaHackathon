"""Safe, code-owned coaching personas for ProofStudy.

Personas alter delivery, never the standard of feedback.  All strings and voice
settings are bounded here so an API value cannot become an arbitrary prompt or
unsafe TTS instruction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    id: str
    label: str
    tone: str
    text_style: str
    tts_rate: float = 1.0
    tts_pitch: float = 1.0
    max_feedback_chars: int = 320

    def __post_init__(self) -> None:
        if not 0.75 <= self.tts_rate <= 1.25:
            raise ValueError("persona TTS rate must be between 0.75 and 1.25")
        if not 0.8 <= self.tts_pitch <= 1.2:
            raise ValueError("persona TTS pitch must be between 0.8 and 1.2")
        if not 80 <= self.max_feedback_chars <= 500:
            raise ValueError("persona feedback limit must be between 80 and 500 characters")


PERSONAS: dict[str, Persona] = {
    "scottish_granny": Persona(
        id="scottish_granny",
        label="Scottish granny",
        tone="warm",
        text_style="Warm, concise and gently direct. Use light Scottish phrasing, never caricature.",
        tts_rate=0.94,
        tts_pitch=1.03,
    ),
    "disappointed_mother": Persona(
        id="disappointed_mother",
        label="Disappointed mother",
        tone="firm",
        text_style="Calm and firm. Name the missed goal without guilt, shame, insults or threats.",
        tts_rate=0.97,
        tts_pitch=1.0,
    ),
    "angry_father": Persona(
        id="angry_father",
        label="Angry father",
        tone="direct",
        text_style="Brief and urgent but controlled. Never shout, insult, threaten or demean.",
        tts_rate=1.04,
        tts_pitch=0.96,
    ),
}
PERSONA_REGISTRY = PERSONAS

# Existing tone values and common UI spellings resolve to a safe registry ID.
TONE_ALIASES: dict[str, str] = {
    "warm": "scottish_granny",
    "gentle": "scottish_granny",
    "kind": "scottish_granny",
    "kind_but_sharp": "scottish_granny",
    "scottish-granny": "scottish_granny",
    "firm": "disappointed_mother",
    "disappointed": "disappointed_mother",
    "disappointed-mother": "disappointed_mother",
    "strict": "angry_father",
    "direct": "angry_father",
    "angry": "angry_father",
    "angry-father": "angry_father",
}

_ABUSIVE = re.compile(
    r"\b(?:idiot|stupid|useless|worthless|pathetic|lazy|failure|hate you|shut up)\b",
    re.IGNORECASE,
)


def resolve_persona_id(value: str | None, *, default: str = "scottish_granny") -> str:
    """Resolve a registry ID or compatibility tone alias, falling back safely."""
    candidate = (value or "").strip().lower().replace(" ", "_")
    if candidate in PERSONAS:
        return candidate
    return TONE_ALIASES.get(candidate, default)


def get_persona(value: str | None = None) -> Persona:
    return PERSONAS[resolve_persona_id(value)]


def safe_feedback_text(text: str, persona: Persona | str | None = None) -> str:
    """Remove abusive wording and enforce the persona's output length bound."""
    selected = persona if isinstance(persona, Persona) else get_persona(persona)
    cleaned = _ABUSIVE.sub("off track", str(text))
    cleaned = re.sub(r"!+", ".", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= selected.max_feedback_chars:
        return cleaned
    shortened = cleaned[: selected.max_feedback_chars - 1].rsplit(" ", 1)[0]
    return shortened.rstrip(" ,;:") + "…"


def list_personas() -> list[Persona]:
    return list(PERSONAS.values())
