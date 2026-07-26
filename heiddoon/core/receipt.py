"""F6 — the receipt: drift autopsy, learner model update, tomorrow's plan.

The compassion principle has to survive contact with the end of a bad session. The
autopsy names a pattern and its trigger rather than listing failures, because
self-forgiveness after a lapse measurably reduces the *next* episode while shame
reliably increases it. This is also where the loop closes: what the session learned
about the student becomes the shape of tomorrow's contract.
"""

from __future__ import annotations

from .. import prompts
from ..providers import CallMeta, Provider
from ..schemas import Event, LearnerModel, Receipt

#: Cap list growth so a learner model carried across many sessions stays a summary
#: rather than an ever-lengthening log.
MAX_LIST_ITEMS = 8


def compute_focus_score(events: list[Event]) -> int:
    """A defensible focus score with no model involved.

    Used as the fallback, and as a sanity check on the model's number: a session
    where the artifact demonstrably moved should never be scored as a failure
    because of one lapse, and this arithmetic is what enforces that.
    """
    checks = [event for event in events if event.kind in ("screen", "camera") and event.on_task is not None]
    if not checks:
        base = 50.0
    else:
        base = 100.0 * sum(1 for event in checks if event.on_task) / len(checks)

    diffs = [event for event in events if event.kind == "diff"]
    if diffs:
        verdicts = [event.detail.get("verdict") for event in diffs]
        if "progress" in verdicts:
            base = max(base, 60.0) + 10.0  # the work moved; that outranks the check-ins
        elif all(verdict == "stalled" for verdict in verdicts):
            base -= 15.0
        elif "padding" in verdicts:
            base -= 5.0

    passed_quizzes = [event for event in events if event.kind == "quiz" and event.detail.get("pass")]
    base += 5.0 * min(2, len(passed_quizzes))

    return int(max(0, min(100, round(base))))


def make_receipt(
    provider: Provider,
    events: list[Event],
    learner: LearnerModel,
    *,
    session_start: float,
) -> tuple[Receipt, CallMeta]:
    """Turn the session's event log into its honest accounting."""
    deterministic_score = compute_focus_score(events)

    if not events:
        receipt = Receipt(
            autopsy="Nothing was recorded this session, so there is no pattern to read yet.",
            tomorrow="Start a session with the screen signal on and give it twenty minutes.",
            focus_score=0,
            learner_model=learner,
        )
        return receipt, CallMeta(
            provider=provider.name, model=provider.model, latency_s=0.0, attempts=0, ok=True
        )

    raw, meta = provider.complete_json(
        prompts.render(
            prompts.RECEIPT,
            events=[event.for_prompt(session_start) for event in events],
            learner=learner.to_dict(),
        ),
        max_tokens=800,
    )

    if not meta.ok:
        receipt = Receipt(
            autopsy=_fallback_autopsy(events),
            tomorrow="Same task, hard material first, one break scheduled twenty minutes in.",
            focus_score=deterministic_score,
            learner_model=learner,
        )
        receipt._repairs.append("model call failed — deterministic receipt")
        return receipt, meta

    receipt = Receipt.from_model(raw)
    receipt.learner_model = _merge_learner(learner, receipt.learner_model)

    # The model tends to score emotionally rather than arithmetically. Where it
    # disagrees sharply with the event log, the log wins.
    if abs(receipt.focus_score - deterministic_score) > 25:
        receipt._repairs.append(
            f"focus_score: model said {receipt.focus_score}, log supports {deterministic_score}"
        )
        receipt.focus_score = deterministic_score

    if not receipt.autopsy:
        receipt.autopsy = _fallback_autopsy(events)
        receipt._repairs.append("autopsy: empty, used deterministic summary")

    receipt._meta = meta.to_dict()
    meta.repairs = list(receipt._repairs)
    return receipt, meta


def _merge_learner(previous: LearnerModel, updated: LearnerModel) -> LearnerModel:
    """Carry forward what the new session had no evidence about.

    Without this, a single session in which entropy never came up would quietly
    erase entropy from the student's weak topics, and the learner model would
    remember only the most recent hour.
    """
    merged = LearnerModel(
        weak_topics=_merge_list(previous.weak_topics, updated.weak_topics),
        strong_topics=_merge_list(previous.strong_topics, updated.strong_topics),
        drift_patterns=_merge_list(previous.drift_patterns, updated.drift_patterns),
        avg_focus_streak_min=updated.avg_focus_streak_min or previous.avg_focus_streak_min,
        best_nudge_style=updated.best_nudge_style or previous.best_nudge_style,
        next_difficulty=updated.next_difficulty,
    )
    # A topic newly demonstrated as strong should stop being listed as weak.
    merged.weak_topics = [topic for topic in merged.weak_topics if topic not in updated.strong_topics]
    return merged


def _merge_list(previous: list[str], updated: list[str]) -> list[str]:
    """Newest first, de-duplicated case-insensitively, capped."""
    seen: set[str] = set()
    combined: list[str] = []
    for item in list(updated) + list(previous):
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            combined.append(item.strip())
    return combined[:MAX_LIST_ITEMS]


def _fallback_autopsy(events: list[Event]) -> str:
    checks = [event for event in events if event.on_task is not None]
    drifts = [event for event in checks if not event.on_task]
    if not checks:
        return "No check-ins were recorded, so there is nothing to read into yet."
    if not drifts:
        return f"No drift in {len(checks)} check-ins. Whatever you did to set this session up, do it again."
    seen = ", ".join(dict.fromkeys(event.seen for event in drifts if event.seen)) or "elsewhere"
    return (
        f"{len(drifts)} of {len(checks)} check-ins drifted, towards: {seen}. "
        "Too short a log to call it a pattern yet — a few more sessions and it will show."
    )
