"""F4 — progress read from the artifact, not from surveilled activity.

The answer to the objection every screen-watcher fails: nobody procrastinates on
their laptop any more. This measures output, so it is device-independent by
construction. Twenty minutes on a phone is an empty diff no matter what the screen
or the camera saw.
"""

from __future__ import annotations

import difflib
import re

from .. import prompts
from ..providers import CallMeta, Provider
from ..schemas import Contract, Diff

_WORD = re.compile(r"\b[\w'-]+\b")

#: Below this, a change is a typo fix or a stray keystroke, not a delta worth a
#: model call — and worth an honest "stalled" rather than a generous "progress".
MIN_INTERESTING_WORDS = 8


def count_words(text: str) -> int:
    return len(_WORD.findall(text or ""))


def net_word_delta(before: str, after: str) -> int:
    """Words genuinely added, ignoring text that merely moved.

    A naive `len(after) - len(before)` reports zero for a rewrite that replaced a
    paragraph with a better one, and reports progress for text pasted in from
    elsewhere. Diffing on words first keeps the number honest about *new* material.
    """
    before_words = _WORD.findall(before or "")
    after_words = _WORD.findall(after or "")
    matcher = difflib.SequenceMatcher(None, before_words, after_words, autojunk=False)
    added = removed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            added += j2 - j1
        elif tag == "delete":
            removed += i2 - i1
        elif tag == "replace":
            added += j2 - j1
            removed += i2 - i1
    return added - removed


def unified_diff(before: str, after: str, context: int = 2) -> str:
    """The changed hunks only — what the model actually needs to judge."""
    return "\n".join(
        difflib.unified_diff(
            (before or "").splitlines(),
            (after or "").splitlines(),
            fromfile="before",
            tofile="after",
            n=context,
            lineterm="",
        )
    )


def judge_delta(
    provider: Provider,
    contract: Contract,
    before: str,
    after: str,
    *,
    minutes: int = 20,
    max_chars: int = 6000,
) -> tuple[Diff, CallMeta]:
    """Judge what changed between two snapshots of the contracted file."""
    delta = net_word_delta(before, after)

    if (before or "").strip() == (after or "").strip():
        # Identical files need no model. Cheap, and on local hardware this is the
        # difference between an instant answer and a minute of waiting.
        diff = Diff(
            delta_words=0,
            substantive=False,
            summary="The file has not changed.",
            quality_note=f"Nothing new in the last {minutes} minutes.",
            verdict="stalled",
        )
        return diff, CallMeta(
            provider=provider.name, model=provider.model, latency_s=0.0, attempts=0, ok=True
        )

    if abs(delta) < MIN_INTERESTING_WORDS:
        diff = Diff(
            delta_words=delta,
            substantive=False,
            summary=f"Only {delta:+d} words changed — edits, not new material.",
            quality_note=f"Nothing substantial added in the last {minutes} minutes.",
            verdict="stalled",
        )
        return diff, CallMeta(
            provider=provider.name, model=provider.model, latency_s=0.0, attempts=0, ok=True
        )

    raw, meta = provider.complete_json(
        prompts.render(
            prompts.ARTIFACT_DIFF,
            contract=contract.for_prompt(),
            minutes=minutes,
            before=_clip(before, max_chars),
            after=_clip(after, max_chars),
        ),
        max_tokens=500,
    )

    if not meta.ok:
        diff = Diff(
            delta_words=delta,
            substantive=abs(delta) >= MIN_INTERESTING_WORDS,
            summary=f"{delta:+d} words (not judged — model unavailable)",
            quality_note=meta.error or "model call failed",
            verdict="stalled",
        )
        diff._repairs.append("model call failed")
        return diff, meta

    diff = Diff.from_model(raw)

    # We can count words exactly; the model cannot, and asking it to guess produces
    # numbers that get quoted. Ours wins.
    if diff.delta_words != delta:
        diff._repairs.append(f"delta_words: model said {diff.delta_words}, counted {delta}")
        diff.delta_words = delta

    # A "progress" verdict on a file that shrank is a contradiction; trust the count.
    if diff.verdict == "progress" and delta < MIN_INTERESTING_WORDS:
        diff._repairs.append(f"verdict: 'progress' contradicted by {delta:+d} net words")
        diff.verdict = "stalled"
        diff.substantive = False

    diff.substantive = diff.verdict == "progress"
    diff._meta = meta.to_dict()
    meta.repairs = list(diff._repairs)
    return diff, meta


def _clip(text: str, limit: int) -> str:
    """Keep the tail when a file is too long — that is where new writing lands."""
    text = text or ""
    if len(text) <= limit:
        return text
    return "…[earlier content trimmed]…\n" + text[-limit:]
