"""F2 — semantic screen and camera verdicts.

The claim this module has to earn: a window-title blocker cannot do this. A lecture
and a cat compilation are the same website; the right module's PDF and the wrong
module's PDF are the same application. Only a judgment about meaning, against this
student's declared task, separates them.
"""

from __future__ import annotations

import re
from typing import Any

from .. import prompts
from ..providers import CallMeta, Provider
from ..schemas import Contract, Verdict

#: Tone is a promise, not a preference. Shame fuels the avoidance cycle the app
#: exists to interrupt, so these are stripped in code rather than merely
#: discouraged in the prompt — a prompt instruction is a request, this is a rule.
_BANNED_PUNCTUATION = re.compile(r"[!]+")
_SHAMING = re.compile(
    r"\b(lazy|pathetic|waste|wasting|shame|shameful|disappoint\w*|failure|pull yourself)\b",
    re.IGNORECASE,
)


def judge_frame(
    provider: Provider,
    contract: Contract,
    image: Any,
    *,
    expect_kind: str | None = None,
) -> tuple[Verdict, CallMeta]:
    """Judge one frame against the contract.

    `expect_kind` is a hint from the caller that already knows whether it grabbed
    the screen or the webcam; it corrects the model rather than trusting it, since
    the frame source is something we know for certain and it does not.
    """
    raw, meta = provider.complete_json(
        prompts.render(prompts.VERDICT, contract=contract.for_prompt()),
        image=image,
        max_tokens=400,
    )

    if not meta.ok:
        # An unreachable model must not become an accusation. Stay silent, stay
        # on-task, and let the event log record that we could not see.
        verdict = Verdict(
            frame_kind=expect_kind or "screen",
            on_task=True,
            seen="(no verdict — model unavailable)",
            reason=meta.error or "model call failed",
            confidence="low",
        )
        verdict._repairs.append("model call failed")
        verdict._meta = meta.to_dict()
        return verdict, meta

    verdict = Verdict.from_model(raw)

    if expect_kind and verdict.frame_kind != expect_kind:
        verdict._repairs.append(f"frame_kind: model said {verdict.frame_kind!r}, source was {expect_kind!r}")
        verdict.frame_kind = expect_kind

    verdict.nudge = _clean_nudge(verdict.nudge, verdict, contract)

    verdict._meta = meta.to_dict()
    meta.repairs = list(verdict._repairs)
    return verdict, meta


def _clean_nudge(nudge: str, verdict: Verdict, contract: Contract) -> str:
    if verdict.on_task:
        # Nothing to say. Silence when the student is working is the feature —
        # an app that comments on success is an app that gets muted.
        return ""

    cleaned = _BANNED_PUNCTUATION.sub(".", nudge).strip()
    if _SHAMING.search(cleaned):
        verdict._repairs.append("nudge: rewritten, model produced shaming language")
        cleaned = ""
    if not cleaned:
        cleaned = _fallback_nudge(contract)
        verdict._repairs.append("nudge: empty, used fallback")
    return cleaned


def _fallback_nudge(contract: Contract) -> str:
    """A nudge that needs no model, in the student's own terms."""
    if contract.why:
        return f"This was the hour for {contract.task}. You said: {contract.why}"
    if contract.task:
        return f"Still here when you want to get back to {contract.task}."
    return "Still here when you want to get back to it."
