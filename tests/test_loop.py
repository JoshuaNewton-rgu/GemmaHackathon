"""End-to-end tests on the mock provider — no network, no model, no GPU.

The point is not to check the model's judgment; it is to check that the plumbing
around the model holds. Every one of these covers something that was actually
broken or absent in the version this replaced.
"""

from __future__ import annotations

import json

import pytest

from heiddoon.config import Settings
from heiddoon.core import bouncer, diff, receipt, verdict
from heiddoon.core.session import Session
from heiddoon.providers import MockProvider, extract_json
from heiddoon.schemas import Contract, Event, LearnerModel, Quiz
from heiddoon.store import Store

CONTRACT = Contract(
    task="thermodynamics chapter 4 (entropy)",
    why="exam on Friday and I do not want another all-nighter",
    allowed=["lecture videos about thermodynamics", "thermodynamics PDFs"],
    blocked=["social media", "entertainment video"],
    artifacts=["notes.md"],
    signals=["screen", "diff"],
)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


@pytest.fixture
def session(store, tmp_path):
    settings = Settings(db_path=tmp_path / "test.db")
    return Session(MockProvider(), CONTRACT, store=store, settings=settings)


# ── JSON extraction ─────────────────────────────────────────────────────────


class TestExtractJson:
    def test_plain(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_leading_prose(self):
        assert extract_json('Sure. Here you go:\n{"a": 1}') == {"a": 1}

    def test_trailing_brace_in_prose(self):
        # The regex this replaced spanned to the last '}' in the string and so
        # produced nothing usable here.
        assert extract_json('{"a": 1}\nHope that helps :}') == {"a": 1}

    def test_nested(self):
        assert extract_json('{"a": {"b": [1, 2]}}') == {"a": {"b": [1, 2]}}

    def test_brace_inside_string(self):
        assert extract_json('{"a": "not } the end"}') == {"a": "not } the end"}

    def test_no_json(self):
        assert extract_json("I would rather not.") is None


# ── reasoning models ────────────────────────────────────────────────────────


class TestThoughtParts:
    """Gemma 4 reasons before answering, and its thinking contains draft JSON.

    Joining every part of the response together — the obvious implementation, and
    what this code did first — meant the brace scanner could return a verdict the
    model had considered and *rejected*. These lock the fix in place.
    """

    @staticmethod
    def _provider():
        from heiddoon.providers.google_api import GoogleProvider

        return GoogleProvider("gemma-4-31b-it", api_key="test-key")

    def test_thought_parts_are_discarded(self):
        payload = {
            "candidates": [{
                "content": {"parts": [
                    {"text": 'Maybe {"on_task": false}? No — it is a lecture.', "thought": True},
                    {"text": '{"on_task": true}'},
                ]},
                "finishReason": "STOP",
            }],
        }
        assert self._provider()._first_text(payload) == '{"on_task": true}'

    def test_the_rejected_draft_is_not_what_gets_parsed(self):
        from heiddoon.providers.base import extract_json

        payload = {
            "candidates": [{
                "content": {"parts": [
                    {"text": 'Draft: {"on_task": false}', "thought": True},
                    {"text": '{"on_task": true}'},
                ]},
                "finishReason": "STOP",
            }],
        }
        assert extract_json(self._provider()._first_text(payload)) == {"on_task": True}

    def test_budget_exhausted_by_thinking_says_so(self):
        from heiddoon.providers.base import ProviderError

        payload = {
            "candidates": [{
                "content": {"parts": [{"text": "thinking…", "thought": True}]},
                "finishReason": "MAX_TOKENS",
            }],
            "usageMetadata": {"thoughtsTokenCount": 340},
        }
        with pytest.raises(ProviderError, match="budget ran out"):
            self._provider()._first_text(payload)

    def test_usage_is_recorded_for_reporting(self):
        provider = self._provider()
        payload = {
            "candidates": [{"content": {"parts": [{"text": "{}"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 5, "thoughtsTokenCount": 115},
        }
        provider._first_text(payload)
        assert provider._last_usage["thought_tokens"] == 115

    def test_reasoning_overhead_is_added_to_the_caller_budget(self):
        # A caller asking for 400 tokens of JSON must not have its whole budget
        # eaten by invisible reasoning.
        provider = self._provider()
        seen = {}

        def fake_generate(prompt, *, image=None, max_tokens=512, temperature=0.2, json_mode=False):
            seen["max_tokens"] = max_tokens
            return '{"ok": true}'

        provider.generate = fake_generate  # type: ignore[method-assign]
        provider.complete_json("prompt", max_tokens=400)
        assert seen["max_tokens"] == 400 + provider.reasoning_overhead_tokens


# ── schema coercion ─────────────────────────────────────────────────────────


class TestCoercion:
    def test_string_bool(self):
        result = verdict.Verdict.from_model({"on_task": "false", "seen": "x"})
        assert result.on_task is False
        assert not result.clean

    def test_missing_on_task_defaults_to_on_task(self):
        # Silence beats a false accusation when the model gives us nothing.
        assert verdict.Verdict.from_model({"seen": "x"}).on_task is True

    def test_comma_string_becomes_list(self):
        result = Contract.from_model({"task": "t", "allowed": "a, b"})
        assert result.allowed == ["a", "b"]

    def test_focus_score_clamped(self):
        from heiddoon.schemas import Receipt

        assert Receipt.from_model({"focus_score": 900}).focus_score == 100

    def test_grade_wire_name(self):
        from heiddoon.schemas import Grade

        grade = Grade.from_model({"pass": True, "feedback": "good"})
        assert grade.passed is True
        assert grade.to_dict()["pass"] is True


# ── the work-diff ───────────────────────────────────────────────────────────


class TestDiff:
    def test_identical_is_stalled_without_a_model_call(self):
        provider = MockProvider()
        result, meta = diff.judge_delta(provider, CONTRACT, "same text here", "same text here")
        assert result.verdict == "stalled"
        assert provider.calls == []  # never asked the model
        assert meta.attempts == 0

    def test_trivial_edit_is_stalled(self):
        provider = MockProvider()
        result, _ = diff.judge_delta(provider, CONTRACT, "a b c d e", "a b c d e f")
        assert result.verdict == "stalled"
        assert provider.calls == []

    def test_net_word_delta_ignores_moved_text(self):
        before = "alpha beta gamma delta"
        after = "delta alpha beta gamma"
        assert diff.net_word_delta(before, after) == 0

    def test_net_word_delta_counts_new_material(self):
        assert diff.net_word_delta("one two", "one two three four five") == 3

    def test_deletion_is_negative(self):
        assert diff.net_word_delta("one two three four", "one two") == -2

    def test_word_count_overrides_the_model(self):
        # The mock always claims delta_words == 0; the real count must win.
        provider = MockProvider()
        before = "short start"
        after = "short start " + " ".join(f"word{n}" for n in range(40))
        result, _ = diff.judge_delta(provider, CONTRACT, before, after)
        assert result.delta_words == 40
        assert any("delta_words" in note for note in result._repairs)


# ── the bouncer ─────────────────────────────────────────────────────────────


class TestBouncer:
    def test_empty_answer_fails_without_a_model_call(self):
        provider = MockProvider()
        grade, _ = bouncer.grade_answer(provider, Quiz(question="q", key_points=["k"]), "   ")
        assert grade.passed is False
        assert provider.calls == []

    def test_evasion_fails(self):
        provider = MockProvider()
        grade, _ = bouncer.grade_answer(provider, Quiz(question="q", key_points=["k"]), "idk")
        assert grade.passed is False

    def test_overlap_fallback_passes_a_good_answer(self):
        quiz = Quiz(
            question="Why does entropy rise in free expansion?",
            key_points=["entropy is a state function", "only the endpoints matter"],
        )
        grade = bouncer._overlap_grade(
            quiz,
            "because entropy is a state function so only the endpoints matter, not the path",
        )
        assert grade.passed is True

    def test_overlap_fallback_rejects_a_bad_answer(self):
        quiz = Quiz(question="q", key_points=["entropy is a state function", "endpoints matter"])
        assert bouncer._overlap_grade(quiz, "I think it goes up because of heat and stuff").passed is False


# ── tone is enforced in code ─────────────────────────────────────────────────


class TestTone:
    def test_nudge_cleared_when_on_task(self):
        result = verdict.Verdict(on_task=True, nudge="get back to work")
        assert verdict._clean_nudge(result.nudge, result, CONTRACT) == ""

    def test_exclamation_marks_removed(self):
        result = verdict.Verdict(on_task=False)
        assert "!" not in verdict._clean_nudge("Back to it!!", result, CONTRACT)

    def test_shaming_language_replaced(self):
        result = verdict.Verdict(on_task=False)
        cleaned = verdict._clean_nudge("Stop being lazy", result, CONTRACT)
        assert "lazy" not in cleaned.lower()
        assert CONTRACT.why in cleaned  # falls back to the student's own words

    def test_fallback_quotes_the_students_reason(self):
        assert "all-nighter" in verdict._fallback_nudge(CONTRACT)


# ── focus score ─────────────────────────────────────────────────────────────


class TestFocusScore:
    def test_all_on_task(self):
        events = [Event(kind="screen", on_task=True) for _ in range(4)]
        assert receipt.compute_focus_score(events) == 100

    def test_half_drifted(self):
        events = [Event(kind="screen", on_task=n % 2 == 0) for n in range(4)]
        assert receipt.compute_focus_score(events) == 50

    def test_real_progress_outranks_a_lapse(self):
        events = [
            Event(kind="screen", on_task=True),
            Event(kind="screen", on_task=False),
            Event(kind="screen", on_task=False),
            Event(kind="diff", detail={"verdict": "progress", "delta_words": 210}),
        ]
        # One third of check-ins on task, but the work demonstrably moved.
        assert receipt.compute_focus_score(events) >= 60

    def test_no_events_is_neutral_not_zero(self):
        assert receipt.compute_focus_score([]) == 50


# ── the learner model survives sessions ─────────────────────────────────────


class TestPersistence:
    def test_events_round_trip(self, session):
        session._record(Event(kind="screen", on_task=False, seen="a cat video", detail={"nudge": "back to it"}))
        events = session.events
        assert len(events) == 1
        assert events[0].seen == "a cat video"
        assert events[0].detail["nudge"] == "back to it"

    def test_learner_model_persists_across_sessions(self, store, tmp_path):
        settings = Settings(db_path=tmp_path / "test.db")
        first = Session(MockProvider(), CONTRACT, store=store, settings=settings)
        first.learner = LearnerModel(weak_topics=["entropy calculations"])
        store.save_learner(first.learner)

        second = Session(MockProvider(), CONTRACT, store=store, settings=settings)
        assert second.learner.weak_topics == ["entropy calculations"]

    def test_merge_keeps_topics_with_no_new_evidence(self):
        previous = LearnerModel(weak_topics=["entropy", "carnot cycles"])
        updated = LearnerModel(weak_topics=["clausius inequality"])
        merged = receipt._merge_learner(previous, updated)
        assert "entropy" in merged.weak_topics
        assert "clausius inequality" in merged.weak_topics

    def test_topic_demonstrated_strong_leaves_the_weak_list(self):
        previous = LearnerModel(weak_topics=["entropy"])
        updated = LearnerModel(strong_topics=["entropy"])
        merged = receipt._merge_learner(previous, updated)
        assert "entropy" not in merged.weak_topics

    def test_snapshot_dedupes_identical_content(self, session):
        session.store.add_snapshot(session.id, "notes.md", "hello")
        session.store.add_snapshot(session.id, "notes.md", "hello")
        session.store.add_snapshot(session.id, "notes.md", "hello there")
        assert session.store.latest_snapshot(session.id, "notes.md")["content"] == "hello there"
        assert session.store.first_snapshot(session.id, "notes.md")["content"] == "hello"

    def test_resume_reattaches_to_the_same_session(self, store, tmp_path):
        settings = Settings(db_path=tmp_path / "test.db")
        original = Session(MockProvider(), CONTRACT, store=store, settings=settings)
        original._record(Event(kind="screen", on_task=True, seen="notes"))

        resumed = Session.resume(MockProvider(), original.id, store=store, settings=settings)
        assert resumed.id == original.id
        assert resumed.contract.task == CONTRACT.task
        assert len(resumed.events) == 1


# ── the artifact watcher ────────────────────────────────────────────────────


class TestArtifactWatcher:
    def test_reports_a_settled_change(self, tmp_path):
        from heiddoon.watchers.artifact import ArtifactWatcher

        path = tmp_path / "notes.md"
        path.write_text("first", encoding="utf-8")
        watcher = ArtifactWatcher([str(path)], settle_s=0.0)

        assert watcher.poll() == []  # nothing has changed yet
        path.write_text("first and second", encoding="utf-8")
        assert watcher.poll() == [str(path)]
        assert watcher.poll() == []  # reported once, not repeatedly

    def test_holds_back_a_file_still_being_written(self, tmp_path):
        from heiddoon.watchers.artifact import ArtifactWatcher

        path = tmp_path / "notes.md"
        path.write_text("first", encoding="utf-8")
        watcher = ArtifactWatcher([str(path)], settle_s=60.0)
        path.write_text("mid-sentence", encoding="utf-8")
        watcher.poll()  # sees the change
        assert watcher.poll() == []  # but will not judge it yet

    def test_missing_file_is_reported_not_crashed(self, tmp_path):
        from heiddoon.watchers.artifact import ArtifactWatcher

        watcher = ArtifactWatcher([str(tmp_path / "nope.md")])
        assert watcher.poll() == []
        assert len(watcher.missing()) == 1


# ── the eval refuses to launder mock output ─────────────────────────────────


class TestEvalHonesty:
    def test_refuses_to_write_results_for_the_mock_provider(self, tmp_path, capsys):
        from heiddoon.evaluate import run_eval

        testset = tmp_path / "testset"
        testset.mkdir()
        (testset / "labels.json").write_text(json.dumps({}), encoding="utf-8")
        out = tmp_path / "eval.json"

        run_eval(MockProvider(), testset, CONTRACT, out_path=out, verbose=False)
        assert not out.exists()
        assert "REFUSING" in capsys.readouterr().out

    def test_synthetic_frames_are_kept_out_of_the_headline(self, tmp_path):
        from PIL import Image

        from heiddoon.evaluate import run_eval

        testset = tmp_path / "testset"
        testset.mkdir()
        Image.new("RGB", (32, 32)).save(testset / "fake.png")
        (testset / "labels.json").write_text(
            json.dumps({"fake.png": {"on_task": False, "kind": "screen", "case": "easy", "source": "synthetic"}}),
            encoding="utf-8",
        )

        report = run_eval(MockProvider(), testset, CONTRACT, verbose=False)
        assert report["headline"]["n"] == 0  # nothing quotable
        assert report["synthetic_only"]["n"] == 1

    def test_missing_frames_are_counted_not_dropped(self, tmp_path):
        from heiddoon.evaluate import run_eval

        testset = tmp_path / "testset"
        testset.mkdir()
        (testset / "labels.json").write_text(
            json.dumps({"never_captured.png": {"on_task": True, "source": "real", "note": "todo"}}),
            encoding="utf-8",
        )

        report = run_eval(MockProvider(), testset, CONTRACT, verbose=False)
        assert len(report["not_run"]) == 1
        assert report["coverage"]["executed"] == 0
