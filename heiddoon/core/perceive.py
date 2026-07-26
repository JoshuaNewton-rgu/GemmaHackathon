"""The perception layer: a frame becomes degrees.

The division of labour matters more than any single number here. The model is asked
only for what genuinely has to be *perceived* — how related the content is, whether
this is the student's own writing, whether it is padding, and how sure it is. Anything
the system can simply *measure* is measured instead: how long the drift has run, how
long since a break, whether the work grew, whether anyone is at the desk.

That split is the difference between an interpretable system and a decorated one. Every
number the rules consume is either something a person could check by looking at the same
frame, or something arithmetic derived from the event log. None of it is a model's
opinion about what should happen.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .. import prompts
from ..providers import CallMeta, Provider
from ..schemas import Contract, Event


def _degree(value: Any, default: float = 0.0) -> float:
    """Coerce a model's number into [0, 1]. Anything unreadable becomes the default."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    # Models sometimes answer a 0-100 scale despite being asked for 0-1.
    if number > 1.0:
        number = number / 100.0 if number <= 100.0 else 1.0
    return max(0.0, min(1.0, number))


@dataclass
class Perception:
    """What was perceived in one frame, as degrees plus the words to show a human."""

    topic_match: float = 0.0
    is_own_work: float = 0.0
    padding: float = 0.0
    confidence: float = 0.0
    seen: str = ""
    reason: str = ""
    work_text: str = ""
    work_source: str = ""
    repairs: list[str] = field(default_factory=list)

    @classmethod
    def from_model(cls, raw: dict[str, Any]) -> Perception:
        repairs: list[str] = []
        for key in ("topic_match", "is_own_work", "padding", "confidence"):
            if key not in raw:
                repairs.append(f"{key}: missing")
        perception = cls(
            topic_match=_degree(raw.get("topic_match")),
            is_own_work=_degree(raw.get("is_own_work")),
            padding=_degree(raw.get("padding")),
            # A missing confidence must read as "unsure", not as "certain". The rule
            # base buys silence with low confidence, so the safe default is the one
            # that keeps the app quiet rather than the one that lets it accuse.
            confidence=_degree(raw.get("confidence"), default=0.0),
            seen=str(raw.get("seen", "")).strip(),
            reason=str(raw.get("reason", "")).strip(),
            work_text=str(raw.get("work_text", "")).strip(),
            work_source=str(raw.get("work_source", "")).strip(),
            repairs=repairs,
        )
        return perception

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic_match": round(self.topic_match, 3),
            "is_own_work": round(self.is_own_work, 3),
            "padding": round(self.padding, 3),
            "confidence": round(self.confidence, 3),
            "seen": self.seen,
            "reason": self.reason,
            "work_source": self.work_source,
        }


def perceive(
    provider: Provider, contract: Contract, image: Any, *, kind: str = "screen"
) -> tuple[Perception, CallMeta]:
    """Read one frame into degrees. Never decides anything."""
    raw, meta = provider.complete_json(
        prompts.render(prompts.PERCEIVE, contract=contract.for_prompt()),
        image=image,
        max_tokens=900,
    )
    if not meta.ok:
        # Zero confidence, which the rule base turns into silence. An unreachable
        # model must not be able to produce an intervention.
        failed = Perception(seen="(nothing perceived — model unavailable)", reason=meta.error)
        failed.repairs.append("model call failed")
        return failed, meta

    perception = Perception.from_model(raw)
    meta.repairs = list(perception.repairs)
    return perception, meta


# ── the measured percepts ───────────────────────────────────────────────────
# Derived from the event log rather than asked of the model, because they are facts
# the system already holds and a model's guess at them would be strictly worse.


def measure_drift(events: list[Event], *, now: float | None = None, ceiling_min: float = 15.0) -> float:
    """How long since the student was last seen on task, scaled to [0, 1].

    Counts from the last on-task frame, or the session's first event if there has
    never been one. `ceiling_min` is where "long" saturates — a quarter of an hour
    away is as bad as the scale needs to express.
    """
    if not events:
        return 0.0
    now = now or time.time()
    on_task = [event for event in events if event.on_task is True]
    since = (on_task[-1].at if on_task else events[0].at)
    return max(0.0, min(1.0, (now - since) / (ceiling_min * 60.0)))


def measure_fatigue(
    started_at: float, last_break_at: float | None, *, now: float | None = None, ceiling_min: float = 50.0
) -> float:
    """Time worked without a break, scaled to [0, 1]."""
    now = now or time.time()
    since = now - (last_break_at or started_at)
    return max(0.0, min(1.0, since / (ceiling_min * 60.0)))


def measure_progress(events: list[Event], *, window_min: float = 30.0, now: float | None = None) -> float:
    """How well the work is moving, from the most recent diff verdicts.

    Reads the artifact, never the activity — which is the one claim in this product
    that the fuzzy layer must not quietly undermine by inferring progress from how
    busy someone looks.
    """
    now = now or time.time()
    recent = [
        event
        for event in events
        if event.kind == "diff" and (now - event.at) <= window_min * 60.0
    ]
    if not recent:
        return 0.0
    latest = recent[-1].detail.get("verdict")
    if latest == "progress":
        return 0.9
    if latest == "padding":
        return 0.3
    return 0.05


def measure_presence(events: list[Event], *, window_min: float = 10.0, now: float | None = None) -> float:
    """Whether the student appears to be there, from camera and idle events."""
    now = now or time.time()
    recent = [
        event
        for event in events
        if event.kind in ("camera", "idle") and (now - event.at) <= window_min * 60.0
    ]
    if not recent:
        return 0.7  # no evidence either way; assume present rather than accuse
    latest = recent[-1]
    if latest.kind == "idle":
        return 0.1
    return 0.9 if latest.on_task else 0.35
