"""A fake provider for tests and offline UI work.

The predecessor of this file was a `MOCK = True` flag inside the notebook that
returned canned verdicts, and the danger it created was real enough to earn a line
in the submission checklist: canned numbers look exactly like measured ones once
they are printed. So this provider is loudly, structurally unquotable — `name` is
"mock", and the eval harness refuses to write a result file when it sees that name.
"""

from __future__ import annotations

import json
from typing import Any

from .base import Provider


class MockProvider(Provider):
    """Deterministic responses keyed off which mechanic is asking.

    Answers are chosen by looking for the schema keys the prompt asks for, so it
    keeps working when prompt wording changes.
    """

    supports_json_mode = True

    def __init__(self, model: str = "mock", **_: Any) -> None:
        super().__init__(model)
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "mock"

    def generate(
        self,
        prompt: str,
        *,
        image: Any = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        self.calls.append(prompt)
        return json.dumps(self._response_for(prompt))

    @staticmethod
    def _response_for(prompt: str) -> dict[str, Any]:
        if "frame_kind" in prompt:
            return {
                "frame_kind": "screen",
                "on_task": False,
                "seen": "MOCK PROVIDER — no model was called",
                "reason": "mock provider: this is not a real verdict",
                "nudge": "This is mock output. Configure a real provider before quoting anything.",
                "confidence": "low",
            }
        if "delta_words" in prompt:
            return {
                "delta_words": 0,
                "substantive": False,
                "summary": "MOCK PROVIDER — no model was called",
                "quality_note": "mock provider",
                "verdict": "stalled",
            }
        if "key_points" in prompt:
            return {"question": "MOCK PROVIDER — no model was called", "key_points": ["mock"]}
        if '"pass"' in prompt or "matched_points" in prompt:
            return {"pass": False, "feedback": "MOCK PROVIDER — no model was called", "matched_points": []}
        if "autopsy" in prompt:
            return {
                "autopsy": "MOCK PROVIDER — no model was called.",
                "tomorrow": "mock provider",
                "focus_score": 0,
                "learner_model": {
                    "weak_topics": [],
                    "strong_topics": [],
                    "drift_patterns": [],
                    "avg_focus_streak_min": 0,
                    "best_nudge_style": "warm",
                    "next_difficulty": "same",
                },
            }
        if '"allowed"' in prompt or '"artifacts"' in prompt:
            return {
                "task": "MOCK PROVIDER — no model was called",
                "why": "mock provider",
                "allowed": [],
                "blocked": [],
                "artifacts": [],
                "signals": ["screen"],
                "tone": "kind_but_sharp",
                "ends": "",
            }
        return {"mock": True}
