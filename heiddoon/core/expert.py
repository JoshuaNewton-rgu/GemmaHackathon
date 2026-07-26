"""The expert agent: tunes the rule base to one student, and says why.

What it may change is deliberately narrow. It proposes **weights**, in [0, 1.5], and
nothing else — not the rules, not the membership functions, not the percepts. Two
reasons, and the second is the important one:

1. A weight change is reversible, bounded, and legible. A student can see that
   `r06` went from 1.0 to 1.2 because they ignored four gentle nudges and responded to
   two firm ones. Nobody can audit a system that rewrites its own rules.
2. The rules encode the product's ethics — never interrupt work that is moving, buy
   silence with uncertainty, ask for nothing already known. An agent free to rewrite
   them is an agent free to optimise those away in pursuit of engagement.

On the profile: it is a study-habit profile, grounded in the event log and in the
procrastination literature where that genuinely applies. It is not a psychological
assessment and the prompt forbids it from reading as one. An LLM emitting
pseudo-clinical claims about a student would be both meaningless and harmful, and the
useful version — "you drift at the first hard step, and firm nudges work on you where
gentle ones do not" — is the one that can actually be acted on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .. import prompts
from ..fuzzy import Rule
from ..providers import CallMeta, Provider
from ..schemas import Event

#: Bounds on what the agent may set. Above 1.5 a single rule would dominate every
#: competing one, which is how a tuned system quietly becomes a rude one.
MIN_WEIGHT = 0.0
MAX_WEIGHT = 1.5

#: Rules whose weight the agent may not touch, because they are the ethical floor
#: rather than a preference to be tuned. `r01` is "never interrupt work that is
#: moving"; `r03` is "stay silent when unsure"; `r15` is "do not ask for what is
#: already proven".
PROTECTED = {"r01", "r03", "r15"}


@dataclass
class WeightChange:
    rule_id: str
    old: float
    new: float
    because: str
    applied: bool = False
    rejected_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "from": round(self.old, 3),
            "to": round(self.new, 3),
            "because": self.because,
            "applied": self.applied,
            "rejected_reason": self.rejected_reason,
        }


@dataclass
class Review:
    changes: list[WeightChange] = field(default_factory=list)
    profile: str = ""
    drift_trigger: str = ""
    what_works: str = ""
    confidence: str = "low"
    evidence_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "changes": [change.to_dict() for change in self.changes],
            "applied_count": sum(1 for change in self.changes if change.applied),
            "profile": self.profile,
            "drift_trigger": self.drift_trigger,
            "what_works": self.what_works,
            "confidence": self.confidence,
            "evidence_note": self.evidence_note,
            # Stated in the payload, not only in the UI, so it travels with the data.
            "disclaimer": (
                "A study-habit profile derived from this session log. Not a psychological "
                "or clinical assessment."
            ),
        }


def summarise_responses(events: list[Event]) -> dict[str, Any]:
    """What actually happened after each intervention.

    This is the evidence the agent is allowed to reason from. Response is measured as
    "was the next frame on task" — crude, but it is observable and it does not require
    the student to report anything.
    """
    counts: dict[str, dict[str, int]] = {
        "gentle": {"shown": 0, "returned": 0},
        "firm": {"shown": 0, "returned": 0},
    }
    for index, event in enumerate(events):
        firmness = event.detail.get("firmness")
        if firmness not in counts:
            continue
        counts[firmness]["shown"] += 1
        for later in events[index + 1 :]:
            if later.kind in ("screen", "camera"):
                if later.on_task:
                    counts[firmness]["returned"] += 1
                break

    quizzes = [event for event in events if event.kind == "quiz"]
    diffs = [event for event in events if event.kind == "diff"]
    return {
        "nudges": counts,
        "quiz_attempts": len(quizzes),
        "quiz_passes": sum(1 for event in quizzes if event.detail.get("pass")),
        "diff_verdicts": [event.detail.get("verdict") for event in diffs],
        "drift_events": [
            {"at_minute": int((event.at - events[0].at) // 60), "seen": event.seen}
            for event in events
            if event.on_task is False
        ][:20],
    }


def review(
    provider: Provider,
    rules: list[Rule],
    events: list[Event],
    *,
    sessions_summary: list[dict[str, Any]] | None = None,
) -> tuple[Review, CallMeta]:
    """Ask the expert agent for weight changes and a profile, then police the answer.

    Every proposal is validated here rather than trusted: an unknown rule id, a
    protected rule, or a weight outside the bounds is recorded as rejected with the
    reason. The agent advises; this function decides what is allowed.
    """
    if len(events) < 4:
        return (
            Review(
                profile="Too little happened to read anything into yet.",
                evidence_note=f"{len(events)} events recorded; a profile needs more than one session.",
                confidence="low",
            ),
            CallMeta(provider=provider.name, model=provider.model, latency_s=0.0, attempts=0, ok=True),
        )

    by_id = {rule.id: rule for rule in rules}
    raw, meta = provider.complete_json(
        prompts.render(
            prompts.EXPERT_REVIEW,
            rules=[
                {"id": rule.id, "rule": rule.text(), "weight": round(rule.weight, 2)}
                for rule in rules
            ],
            history=sessions_summary or [],
            responses=summarise_responses(events),
        ),
        max_tokens=1400,
    )

    if not meta.ok:
        return (
            Review(profile="Could not review this session.", evidence_note=meta.error, confidence="low"),
            meta,
        )

    result = Review(
        profile=str(raw.get("profile", "")).strip(),
        drift_trigger=str(raw.get("drift_trigger", "")).strip(),
        what_works=str(raw.get("what_works", "")).strip(),
        confidence=str(raw.get("confidence", "low")).strip().lower(),
        evidence_note=str(raw.get("evidence_note", "")).strip(),
    )
    if result.confidence not in ("low", "medium", "high"):
        result.confidence = "low"

    for proposal in raw.get("weight_changes") or []:
        if not isinstance(proposal, dict):
            continue
        rule_id = str(proposal.get("rule_id", "")).strip()
        rule = by_id.get(rule_id)
        try:
            new_weight = float(proposal.get("to"))
        except (TypeError, ValueError):
            continue

        change = WeightChange(
            rule_id=rule_id,
            old=rule.weight if rule else 0.0,
            new=new_weight,
            because=str(proposal.get("because", "")).strip(),
        )
        if rule is None:
            change.rejected_reason = "no such rule"
        elif rule_id in PROTECTED:
            change.rejected_reason = (
                "protected: this rule is the product's ethical floor, not a preference"
            )
        elif not MIN_WEIGHT <= new_weight <= MAX_WEIGHT:
            change.rejected_reason = f"weight must be between {MIN_WEIGHT} and {MAX_WEIGHT}"
        elif abs(new_weight - rule.weight) < 0.05:
            change.rejected_reason = "change too small to be meaningful"
        elif not change.because:
            change.rejected_reason = "no justification given"
        else:
            change.applied = True
        result.changes.append(change)

    return result, meta


def apply_changes(rules: list[Rule], review_result: Review) -> list[Rule]:
    """Apply the accepted changes, recording each on the rule it altered.

    The history line is the audit trail: a weight that has been tuned carries the
    reason it moved, so the rule base explains its own drift from the shipped default.
    """
    by_id = {rule.id: rule for rule in rules}
    for change in review_result.changes:
        if not change.applied:
            continue
        rule = by_id.get(change.rule_id)
        if rule is None:
            continue
        rule.history.append(
            f"{change.old:.2f} → {change.new:.2f}: {change.because}"
        )
        rule.weight = change.new
        rule.tuned = True
    return rules
