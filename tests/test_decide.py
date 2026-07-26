"""Tests for the acting thresholds — when the rules are allowed to interrupt someone.

Separate from `test_fuzzy.py`, which covers the engine's arithmetic. This file covers
the policy layer in `core/decide.py`: given that the rules concluded something, is it
strong enough to spend a student's attention on?

That distinction is the bug these tests were written for. Defuzzification is a weighted
average of set centroids, so it divides the firing strength back out — when one output
set is active the value is that set's centroid whatever strength produced it. Gating on
that value let a rule that was 3% true interrupt exactly as readily as one that was 75%
true. Everything below is the guard against it coming back.
"""

from __future__ import annotations

import json
import time
from typing import Any

from heiddoon.core.decide import ACT_STRENGTH, ASK_STRENGTH, decide
from heiddoon.fuzzy import default_rules, engine
from heiddoon.providers.mock import MockProvider
from heiddoon.schemas import Contract

CONTRACT = Contract(
    task="thermodynamics ch.4 — entropy",
    why="exam on Thursday",
    allowed=["lectures", "course PDFs"],
    blocked=["social media", "entertainment"],
    artifacts=["notes_thermo.md"],
    signals=["screen", "diff", "idle"],
)

FULL_INPUT = {
    "topic_match": 0.5,
    "is_own_work": 0.5,
    "padding": 0.0,
    "confidence": 0.9,
    "drift": 0.0,
    "fatigue": 0.0,
    "progress": 0.0,
    "presence": 0.9,
}


class PerceivingProvider(MockProvider):
    """Returns the percepts a test asks for, so the rules are the only variable."""

    def __init__(self, **percepts: Any) -> None:
        super().__init__()
        self.percepts = {
            "topic_match": 0.5,
            "is_own_work": 0.5,
            "padding": 0.0,
            "confidence": 0.9,
            "seen": "a page of something",
            "reason": "because the test said so",
            "work_text": "",
            "work_source": "",
            **percepts,
        }

    def generate(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append(prompt)
        if "topic_match" in prompt:
            return json.dumps(self.percepts)
        if '"line"' in prompt:
            return json.dumps({"line": "This was the hour for entropy."})
        return super().generate(prompt, **kwargs)


def _infer(**overrides: float):
    return engine().infer(default_rules(), {**FULL_INPUT, **overrides})


# ── the defect, stated as arithmetic ────────────────────────────────────────


class TestActivationIsNotTheDefuzzifiedValue:
    """Why `outputs` cannot be used to decide whether to act."""

    def test_the_value_is_identical_however_weakly_the_rule_fired(self):
        barely = _infer(topic_match=0.44, drift=0.5, is_own_work=0.0)
        clearly = _infer(topic_match=0.20, drift=0.5, is_own_work=0.0)

        # Same word, same number — the value carries no information about strength.
        assert barely.output_words["nudge"] == clearly.output_words["nudge"] == "gentle"
        assert barely.outputs["nudge"] == clearly.outputs["nudge"]

        # The activation is where the difference lives, which is why it exists.
        assert barely.activation["nudge"] < 0.15
        assert clearly.activation["nudge"] > 0.60

    def test_activation_travels_in_the_trace(self):
        decision = _infer(topic_match=0.02, drift=0.95)
        assert decision.to_dict()["activation"]["nudge"] > 0.5

    def test_nothing_fired_reads_as_the_default_not_as_an_error(self):
        """No rule has an opinion about the page here: the work is neither proven nor
        invisible. The student-facing sentence has to say that nothing happened, not
        that something went wrong."""
        decision = _infer(is_own_work=0.5, progress=0.5, fatigue=0.0)
        assert "ask_page" not in decision.output_words
        assert "silence is the default" in decision.why("ask_page")


# ── nudges ──────────────────────────────────────────────────────────────────


class TestNudgeThreshold:
    def _outcome(self, *, started_min_ago: float = 1.0, **percepts: Any):
        return decide(
            PerceivingProvider(**percepts),
            CONTRACT,
            image=None,
            rules=default_rules(),
            events=[],
            started_at=time.time() - started_min_ago * 60,
        )

    def test_a_barely_true_rule_does_not_interrupt(self):
        """topic_match 0.44 is 3% "low". That is not grounds to speak to someone."""
        outcome = self._outcome(topic_match=0.44, is_own_work=0.0)
        assert outcome.firmness == "gentle"  # the rules did conclude something…
        assert outcome.decision.activation["nudge"] < ACT_STRENGTH
        assert outcome.act is False  # …and it was far too weak to act on
        assert outcome.nudge_line == ""

    def test_a_clearly_true_rule_does_interrupt(self):
        outcome = self._outcome(topic_match=0.02, is_own_work=0.0)
        assert outcome.decision.activation["nudge"] >= ACT_STRENGTH
        assert outcome.act is True
        assert outcome.nudge_line

    def test_an_unreachable_model_cannot_produce_an_intervention(self):
        """Perception fails to zero confidence, and the rule base turns that into
        silence. The failure mode has to be quiet rather than accusatory."""
        outcome = self._outcome(confidence=0.0, topic_match=0.0)
        assert outcome.act is False


# ── asking to see the page, the only signal that costs the student ──────────


class TestAskPageThreshold:
    def _outcome(self, *, started_min_ago: float, **percepts: Any):
        return decide(
            PerceivingProvider(**percepts),
            CONTRACT,
            image=None,
            rules=default_rules(),
            events=[],
            started_at=time.time() - started_min_ago * 60,
            write_line=False,
        )

    def test_a_student_on_task_is_not_asked_to_prove_it(self):
        """The case that was live: watching a lecture on the contracted topic, ten
        minutes in, and the app asks for a photo of your page off a rule firing at
        0.16 — because it was the only rule with an opinion, so it won by default."""
        outcome = self._outcome(started_min_ago=10, topic_match=0.9, is_own_work=0.1)
        assert outcome.ask_page == "no"

    def test_a_long_stretch_with_nothing_of_theirs_on_screen_does_ask(self):
        """Forty minutes in, nothing on screen is theirs, nothing has moved. This is
        the handwriting case the rule was written for, and it is worth an ask."""
        outcome = self._outcome(started_min_ago=40, topic_match=0.6, is_own_work=0.05)
        assert outcome.decision.activation["ask_page"] >= ASK_STRENGTH
        assert outcome.ask_page == "yes"

    def test_the_tired_case_is_reachable_at_all(self):
        """Regression: the clause used to be `fatigue is medium`, whose membership
        falls back to zero above 0.75 — so the rule could never fire for the very
        student most likely to have moved to paper."""
        decision = _infer(fatigue=0.8, progress=0.0, is_own_work=0.05, topic_match=0.6)
        assert decision.activation.get("ask_page", 0.0) >= ASK_STRENGTH
