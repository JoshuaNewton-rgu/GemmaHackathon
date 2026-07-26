"""Tests for the interpretable decision layer.

The engine is pure arithmetic, so these need no model, no network and no GPU — which
is the point. The claim being made to a judge is that every intervention is traceable
and checkable; that claim is only worth anything if the tracing is itself tested.
"""

from __future__ import annotations

import pytest

from heiddoon.core.perceive import (
    Perception,
    measure_drift,
    measure_fatigue,
    measure_presence,
    measure_progress,
)
from heiddoon.fuzzy import default_rules, engine, parse_rule, validate
from heiddoon.fuzzy.rules import RuleSyntaxError
from heiddoon.fuzzy.sets import three_way
from heiddoon.schemas import Event

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


def scenario(**overrides: float) -> dict[str, float]:
    return {**FULL_INPUT, **overrides}


# ── membership functions ────────────────────────────────────────────────────


class TestFuzzySets:
    def test_shoulders_saturate(self):
        variable = three_way("x", "x")
        assert variable.memberships(0.0)["low"] == 1.0
        assert variable.memberships(1.0)["high"] == 1.0

    def test_sets_overlap_at_the_crossovers(self):
        """Partial membership at the boundaries is the nuance a threshold destroys.

        Not at 0.5 — the midpoint of a three-way partition is purely medium, and that
        is what makes "medium" mean anything. The overlap lives at the crossovers.
        """
        memberships = three_way("x", "x").memberships(0.35)
        assert sum(1 for degree in memberships.values() if degree > 0) >= 2

    def test_every_value_belongs_to_something(self):
        """No input may arrive that the rules cannot describe for lack of a word."""
        variable = three_way("x", "x")
        for step in range(0, 101):
            value = step / 100.0
            assert max(variable.memberships(value).values()) > 0, f"nothing covers {value}"

    def test_membership_is_bounded(self):
        variable = three_way("x", "x")
        for value in (-5.0, 0.0, 0.37, 1.0, 42.0):
            for degree in variable.memberships(value).values():
                assert 0.0 <= degree <= 1.0

    def test_strongest_word_reads_sensibly(self):
        variable = three_way("x", "x")
        assert variable.strongest(0.02) == "low"
        assert variable.strongest(0.5) == "medium"
        assert variable.strongest(0.98) == "high"


# ── the rule language ───────────────────────────────────────────────────────


class TestRuleLanguage:
    def test_round_trips_through_text(self):
        """The text is the canonical form, so parsing and rendering must agree —
        otherwise the sentence shown to a student is not the rule that fired."""
        original = "IF topic_match is low AND drift is long THEN nudge is firm"
        assert parse_rule(original).text() == original

    def test_or_is_preserved(self):
        rule = parse_rule("IF presence is absent OR drift is long THEN nudge is firm")
        assert rule.connective == "or"
        assert "OR" in rule.text()

    def test_negation(self):
        rule = parse_rule("IF progress is not strong THEN ask_page is maybe")
        assert rule.when[0].negated
        assert rule.when[0].degree({"progress": {"strong": 0.25}}) == pytest.approx(0.75)

    def test_and_takes_the_weakest_clause(self):
        rule = parse_rule("IF a is low AND b is low THEN nudge is firm")
        strength, _ = rule.strength({"a": {"low": 0.9}, "b": {"low": 0.2}})
        assert strength == pytest.approx(0.2)

    def test_or_takes_the_strongest_clause(self):
        rule = parse_rule("IF a is low OR b is low THEN nudge is firm")
        strength, _ = rule.strength({"a": {"low": 0.9}, "b": {"low": 0.2}})
        assert strength == pytest.approx(0.9)

    def test_weight_scales_strength(self):
        rule = parse_rule("IF a is low THEN nudge is firm", weight=0.5)
        strength, _ = rule.strength({"a": {"low": 1.0}})
        assert strength == pytest.approx(0.5)

    def test_bad_syntax_names_the_offending_text(self):
        with pytest.raises(RuleSyntaxError, match="nonsense"):
            parse_rule("nonsense")


# ── the shipped rule base ───────────────────────────────────────────────────


class TestRuleBase:
    def test_every_rule_parses_and_references_real_names(self):
        """A rule naming a variable that does not exist can never fire, and a rule
        base silently containing one is a rule base nobody can trust."""
        assert validate(default_rules()) == []

    def test_rule_ids_are_unique(self):
        ids = [rule.id for rule in default_rules()]
        assert len(ids) == len(set(ids))

    def test_every_rule_says_why_it_exists(self):
        for rule in default_rules():
            assert rule.because, f"{rule.id} has no rationale"


# ── the decisions the rules actually reach ──────────────────────────────────


class TestDecisions:
    @staticmethod
    def _decide(**overrides: float):
        return engine().infer(default_rules(), scenario(**overrides))

    def test_work_in_progress_is_never_interrupted(self):
        """The highest-weighted silence rule, and the one that matters most: breaking
        concentration to comment on it is the worst thing a focus tool can do."""
        decision = self._decide(progress=0.9, topic_match=0.9, is_own_work=0.9)
        assert decision.output_words["nudge"] == "silent"

    def test_long_drift_earns_a_firm_word(self):
        decision = self._decide(topic_match=0.02, drift=0.95, is_own_work=0.0)
        assert decision.output_words["nudge"] == "firm"

    def test_brief_drift_is_only_gentle(self):
        decision = self._decide(topic_match=0.02, drift=0.05, is_own_work=0.0)
        assert decision.output_words["nudge"] == "gentle"

    def test_low_confidence_buys_silence(self):
        """An uncertain reading must not become an accusation."""
        decision = self._decide(topic_match=0.02, drift=0.95, confidence=0.05)
        assert decision.output_words["nudge"] == "silent"

    def test_thinking_over_your_own_work_is_not_drift(self):
        """Staring at your own notes having written nothing is the hardest part of
        studying, and the rule base must not punish it."""
        decision = self._decide(progress=0.0, is_own_work=0.95, topic_match=0.8, drift=0.05)
        assert decision.output_words["nudge"] == "silent"

    def test_tired_and_stalled_urges_a_break(self):
        decision = self._decide(fatigue=0.95, progress=0.0)
        assert decision.output_words["break_offer"] == "urge"

    def test_tired_but_flowing_only_mentions_one(self):
        decision = self._decide(fatigue=0.95, progress=0.9)
        assert decision.output_words["break_offer"] == "mention"

    def test_proven_progress_is_never_asked_to_prove_itself(self):
        """The rule the whole intrusion policy turns on."""
        decision = self._decide(progress=0.95)
        assert decision.output_words["ask_page"] == "no"

    def test_blind_to_the_work_asks_for_the_page(self):
        decision = self._decide(progress=0.0, is_own_work=0.05, fatigue=0.5, topic_match=0.5)
        assert decision.output_words.get("ask_page") == "yes"


# ── the audit trail, which is the actual deliverable ────────────────────────


class TestExplanation:
    def test_the_trace_names_the_rules_that_decided(self):
        decision = engine().infer(default_lens := default_rules(), scenario(topic_match=0.02, drift=0.95))
        assert decision.fired
        top = decision.top_rules(1)[0]
        assert top.rule.id in {rule.id for rule in default_lens}
        assert 0.0 < top.strength <= 1.5

    def test_every_fired_rule_reports_each_clause_degree(self):
        decision = engine().infer(default_rules(), scenario(topic_match=0.02, drift=0.95))
        for item in decision.fired:
            assert len(item.clause_degrees) == len(item.rule.when)

    def test_the_explanation_quotes_degrees(self):
        decision = engine().infer(default_rules(), scenario(topic_match=0.02, drift=0.95))
        why = decision.why("nudge")
        assert "%" in why and "because" in why

    def test_nothing_matching_is_reported_as_such(self):
        """"No rule covers this" is a finding about the rule base, not silence."""
        decision = engine().infer([parse_rule("IF topic_match is high THEN nudge is firm")], scenario(topic_match=0.0))
        assert decision.fired == []
        why = decision.why().lower()
        assert "no rule" in why and "silence is the default" in why

    def test_an_unknown_percept_cannot_silently_fire(self):
        decision = engine().infer([parse_rule("IF nonexistent is low THEN nudge is firm")], scenario())
        assert decision.fired == []

    def test_the_trace_serialises_for_the_ui(self):
        import json

        decision = engine().infer(default_rules(), scenario(topic_match=0.02, drift=0.9))
        json.dumps(decision.to_dict())  # must not raise


# ── measured percepts, which are not the model's opinion ───────────────────


class TestMeasuredPercepts:
    def test_drift_grows_with_time_since_on_task(self):
        now = 10_000.0
        events = [Event(kind="screen", on_task=True, at=now - 600)]
        assert measure_drift(events, now=now) == pytest.approx(10 / 15, abs=0.01)

    def test_drift_is_zero_when_just_seen_on_task(self):
        now = 10_000.0
        assert measure_drift([Event(kind="screen", on_task=True, at=now)], now=now) == 0.0

    def test_fatigue_resets_after_a_break(self):
        now = 10_000.0
        long_session = measure_fatigue(now - 3000, None, now=now)
        after_break = measure_fatigue(now - 3000, now - 60, now=now)
        assert long_session > after_break

    def test_progress_reads_the_diff_not_the_activity(self):
        now = 10_000.0
        assert measure_progress([Event(kind="diff", at=now, detail={"verdict": "progress"})], now=now) > 0.8
        assert measure_progress([Event(kind="diff", at=now, detail={"verdict": "padding"})], now=now) < 0.5
        assert measure_progress([Event(kind="diff", at=now, detail={"verdict": "stalled"})], now=now) < 0.1

    def test_no_evidence_assumes_present_rather_than_accusing(self):
        assert measure_presence([], now=10_000.0) >= 0.5

    def test_idle_reads_as_absent(self):
        now = 10_000.0
        assert measure_presence([Event(kind="idle", on_task=False, at=now)], now=now) < 0.2


# ── perception coercion ────────────────────────────────────────────────────


class TestPerception:
    def test_percent_scale_is_rescued(self):
        """Models occasionally answer 0-100 despite being asked for 0-1."""
        assert Perception.from_model({"topic_match": 85}).topic_match == pytest.approx(0.85)

    def test_missing_confidence_reads_as_unsure(self):
        """The safe default is the one that keeps the app quiet, not the one that
        lets it accuse."""
        assert Perception.from_model({"topic_match": 0.9}).confidence == 0.0

    def test_unparseable_degrees_do_not_raise(self):
        perception = Perception.from_model({"topic_match": "very high", "confidence": None})
        assert perception.topic_match == 0.0
        assert perception.repairs


# ── the interpretable path, end to end ──────────────────────────────────────


class TestInterpretableSession:
    """Integration cover for the path the product actually runs by default."""

    @staticmethod
    def _session(store, tmp_path, monkeypatch, perception):
        from heiddoon.config import Settings
        from heiddoon.core import decide as decide_mod
        from heiddoon.core import perceive as perceive_mod
        from heiddoon.core.session import Session
        from heiddoon.providers import CallMeta, MockProvider
        from heiddoon.schemas import Contract

        provider = MockProvider()
        meta = CallMeta(provider="mock", model="mock", latency_s=0.0, attempts=1, ok=True)
        monkeypatch.setattr(perceive_mod, "perceive", lambda *a, **k: (perception, meta))
        monkeypatch.setattr(decide_mod.perceive_mod, "perceive", lambda *a, **k: (perception, meta))
        monkeypatch.setattr(decide_mod, "write_nudge", lambda *a, **k: "a written line")

        contract = Contract(task="compilers — tokenisation", why="coursework Friday", signals=["screen"])
        settings = Settings(db_path=tmp_path / "fuzzy.db", interpretable=True)
        return Session(provider, contract, store=store, settings=settings)

    @pytest.fixture
    def store(self, tmp_path):
        from heiddoon.store import Store

        return Store(tmp_path / "fuzzy.db")

    def test_a_clear_drift_produces_a_nudge_and_a_trace(self, store, tmp_path, monkeypatch):
        perception = Perception(
            topic_match=0.02, is_own_work=0.0, padding=0.0, confidence=0.95, seen="a cat video"
        )
        session = self._session(store, tmp_path, monkeypatch, perception)
        # Backdate the session so `drift` measures as long.
        session.started_at -= 20 * 60
        session._record(Event(kind="screen", on_task=False, seen="a cat video", at=session.started_at))

        outcome = session.judge_frame(object(), kind="screen")
        assert outcome.act is True
        assert outcome.firmness == "firm"
        assert outcome.nudge_line == "a written line"
        assert session.last_trace["trace"]["fired"], "no rules recorded in the trace"

    def test_an_unclear_frame_never_accuses(self, store, tmp_path, monkeypatch):
        """The safety property: uncertainty must not become an intervention."""
        perception = Perception(
            topic_match=0.02, is_own_work=0.0, padding=0.0, confidence=0.05, seen="something blurry"
        )
        session = self._session(store, tmp_path, monkeypatch, perception)
        session.started_at -= 20 * 60
        outcome = session.judge_frame(object(), kind="screen")
        assert outcome.act is False
        assert outcome.nudge_line == ""

    def test_every_event_carries_the_rules_that_caused_it(self, store, tmp_path, monkeypatch):
        """Auditability of the whole session, not just the latest frame."""
        perception = Perception(topic_match=0.02, confidence=0.9, seen="a cat video")
        session = self._session(store, tmp_path, monkeypatch, perception)
        session.started_at -= 20 * 60
        session.judge_frame(object(), kind="screen")

        event = session.events[-1]
        assert event.detail["fired"], "no rule ids on the event"
        assert all("id" in item and "strength" in item for item in event.detail["fired"])
        assert event.detail["percepts"]["confidence"] == 0.9
        assert "because" in event.detail["why"]

    def test_tuned_weights_survive_a_new_session(self, store, tmp_path, monkeypatch):
        perception = Perception(topic_match=0.9, confidence=0.9, seen="notes")
        first = self._session(store, tmp_path, monkeypatch, perception)
        target = next(rule for rule in first.rules if rule.id == "r06")
        target.weight = 1.25
        target.tuned = True
        first.save_rules()

        second = self._session(store, tmp_path, monkeypatch, perception)
        reloaded = next(rule for rule in second.rules if rule.id == "r06")
        assert reloaded.weight == pytest.approx(1.25)
        assert reloaded.tuned


class TestExpertAgent:
    """The agent advises; the code decides what is allowed."""

    def test_protected_rules_cannot_be_weakened(self):
        from heiddoon.core.expert import PROTECTED, Review, WeightChange, apply_changes

        rules = default_rules()
        protected_id = sorted(PROTECTED)[0]
        before = next(rule for rule in rules if rule.id == protected_id).weight
        review = Review(changes=[WeightChange(protected_id, before, 0.1, "because", applied=False)])
        apply_changes(rules, review)
        assert next(rule for rule in rules if rule.id == protected_id).weight == before

    def test_an_applied_change_records_its_reason_on_the_rule(self):
        from heiddoon.core.expert import Review, WeightChange, apply_changes

        rules = default_rules()
        review = Review(
            changes=[WeightChange("r06", 1.0, 1.2, "ignored four gentle nudges", applied=True)]
        )
        apply_changes(rules, review)
        rule = next(item for item in rules if item.id == "r06")
        assert rule.weight == pytest.approx(1.2)
        assert rule.tuned
        assert "ignored four gentle nudges" in rule.history[0]

    def test_a_thin_log_declines_to_profile(self):
        from heiddoon.core.expert import review as expert_review
        from heiddoon.providers import MockProvider

        provider = MockProvider()
        result, _ = expert_review(provider, default_rules(), [Event(kind="screen", on_task=True)])
        assert provider.calls == []  # nothing asked of the model
        assert result.confidence == "low"

    def test_responses_are_measured_not_asked_for(self):
        from heiddoon.core.expert import summarise_responses

        events = [
            Event(kind="screen", on_task=False, at=100, detail={"firmness": "gentle"}),
            Event(kind="screen", on_task=False, at=200),   # ignored it
            Event(kind="screen", on_task=False, at=300, detail={"firmness": "firm"}),
            Event(kind="screen", on_task=True, at=400),    # came back
        ]
        summary = summarise_responses(events)
        assert summary["nudges"]["gentle"] == {"shown": 1, "returned": 0}
        assert summary["nudges"]["firm"] == {"shown": 1, "returned": 1}

    def test_the_profile_carries_its_own_disclaimer(self):
        from heiddoon.core.expert import Review

        assert "Not a psychological" in Review().to_dict()["disclaimer"]
