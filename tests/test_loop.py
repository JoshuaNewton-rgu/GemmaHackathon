"""End-to-end tests on the mock provider — no network, no model, no GPU.

The point is not to check the model's judgment; it is to check that the plumbing
around the model holds. Every one of these covers something that was actually
broken or absent in the version this replaced.
"""

from __future__ import annotations

import json
import time

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

    def test_a_real_answer_goes_through_the_model_path(self):
        """Covers the branch every other bouncer test short-circuits past.

        The deterministic guards (too short, evasion) return before the model is
        called, so nothing here exercised grading proper — and a NameError on that
        path would have reached a user rather than the suite.
        """
        provider = MockProvider()
        quiz = Quiz(question="Why does entropy rise in free expansion?", key_points=["state function"])
        grade, meta = bouncer.grade_answer(
            provider, quiz, "Because entropy is a state function, only the endpoints matter."
        )
        assert provider.calls, "the model was never asked to grade"
        assert meta.ok
        assert isinstance(grade.passed, bool)

    def test_exclamation_marks_are_stripped_from_feedback(self):
        """The product promises a voice without them, and grading is where the
        model most wants to cheer."""
        provider = MockProvider()
        monkey = Quiz(question="q", key_points=["k"])
        grade, _ = bouncer.grade_answer(provider, monkey, "a genuine attempt at the real answer here")
        assert "!" not in grade.feedback

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

    def test_empty_notes_do_not_produce_an_invented_question(self):
        """With no notes, asking the model anyway invents something irrelevant.

        Observed live: an empty notes string produced a question about scientific
        theories versus laws for a student revising thermodynamics. Confidently
        irrelevant is worse than an error, so the topic prompt is used instead.
        """
        provider = MockProvider()
        bouncer.ask_question(provider, "", contract=CONTRACT)
        assert len(provider.calls) == 1
        # The topic prompt, not the notes prompt.
        assert "have not seen your notes" in provider.calls[0] or "contracted topic" in provider.calls[0]

    def test_notes_are_used_when_there_are_enough_of_them(self):
        provider = MockProvider()
        notes = "Entropy is a state function so only the endpoints matter, not the path taken."
        quiz, _ = bouncer.ask_question(provider, notes, contract=CONTRACT)
        assert "Notes:" in provider.calls[0]
        assert quiz.source == "your own notes"

    def test_the_source_is_honest_about_the_topic_fallback(self):
        quiz, _ = bouncer.ask_question(MockProvider(), "", contract=CONTRACT)
        assert "not seen your notes" in quiz.source

    def test_no_notes_and_no_task_asks_nothing_at_all(self):
        provider = MockProvider()
        quiz, _ = bouncer.ask_question(provider, "", contract=Contract())
        assert quiz.question == ""
        assert provider.calls == []  # nothing invented from nothing

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


# ── the student's data is the student's ─────────────────────────────────────


class TestExportAndDelete:
    """Export and delete are product features, not admin tools.

    "Monitoring you opted into" only means something if you can see all of it and
    take it away, so both are covered like any other mechanic.
    """

    def test_export_contains_the_session_and_its_events(self, session):
        session._record(Event(kind="screen", on_task=True, seen="notes open"))
        session.store.add_snapshot(session.id, "notes.md", "entropy is a state function")

        payload = session.store.export_all()
        assert len(payload["sessions"]) == 1
        assert payload["sessions"][0]["contract"]["task"] == CONTRACT.task
        assert len(payload["events"]) == 1
        assert payload["events"][0]["seen"] == "notes open"
        assert payload["artifact_snapshots"][0]["content"] == "entropy is a state function"

    def test_export_is_json_serialisable(self, session):
        session._record(Event(kind="camera", on_task=False, seen="phone in hand"))
        json.dumps(session.store.export_all())  # must not raise

    def test_export_holds_no_frame(self, session):
        """The structural guarantee: there is no field an image could live in."""
        session._record(Event(kind="screen", on_task=True, seen="notes"))
        blob = json.dumps(session.store.export_all()).lower()
        for forbidden in ("image", "jpeg", "png", "base64", "frame_data"):
            assert forbidden not in blob

    def test_delete_removes_everything_and_reports_counts(self, session):
        session._record(Event(kind="screen", on_task=True, seen="notes"))
        session.store.add_snapshot(session.id, "notes.md", "content")
        session.store.save_learner(LearnerModel(weak_topics=["entropy"]))

        removed = session.store.delete_all()
        assert removed["sessions"] == 1
        assert removed["events"] == 1
        assert removed["snapshots"] == 1

        assert session.store.counts() == {"sessions": 0, "events": 0, "snapshots": 0, "verdicts": 0}
        assert session.store.get_learner().weak_topics == []
        assert session.store.recent_sessions() == []

    def test_delete_on_an_empty_store_is_harmless(self, store):
        assert store.delete_all()["sessions"] == 0

    def test_recent_verdicts_are_newest_first_and_frames_only(self, session):
        session._record(Event(kind="screen", on_task=True, seen="first", at=1000.0))
        session._record(Event(kind="diff", seen="notes.md", at=1001.0))
        session._record(Event(kind="camera", on_task=False, seen="second", at=1002.0))

        recent = session.store.recent_verdicts(limit=3)
        assert [entry["seen"] for entry in recent] == ["second", "first"]  # diff excluded

    def test_store_survives_its_database_being_deleted_underneath_it(self, tmp_path):
        """Reproduces a live failure: the db file was removed while the app ran.

        sqlite3.connect() silently creates an empty file, so the next connection
        succeeded against a database with no tables and every write failed with
        "no such table: events" from deep inside a request handler. Creating the
        schema once in __init__ is not enough.
        """
        store = Store(tmp_path / "fragile.db")
        session_id = store.start_session(CONTRACT)
        store.add_event(session_id, Event(kind="screen", on_task=True, seen="before"))

        (tmp_path / "fragile.db").unlink()  # the tidy-up that broke it

        recovered = store.start_session(CONTRACT)
        store.add_event(recovered, Event(kind="screen", on_task=True, seen="after"))
        assert [event.seen for event in store.events(recovered)] == ["after"]

    def test_writing_to_a_vanished_session_raises_a_recoverable_error(self, tmp_path):
        """Not sqlite3.IntegrityError — the caller needs something it can handle.

        After the file is deleted the schema comes back but the session row does
        not, so the insert fails the foreign key. That surfaced as a 500.
        """
        from heiddoon.store import SessionGone

        store = Store(tmp_path / "gone.db")
        session_id = store.start_session(CONTRACT)
        (tmp_path / "gone.db").unlink()

        with pytest.raises(SessionGone):
            store.add_event(session_id, Event(kind="screen", on_task=True, seen="orphan"))
        with pytest.raises(SessionGone):
            store.add_snapshot(session_id, "notes.md", "orphan")

    def test_a_second_store_on_the_same_file_shares_the_schema(self, tmp_path):
        first = Store(tmp_path / "shared.db")
        session_id = first.start_session(CONTRACT)
        second = Store(tmp_path / "shared.db")
        second.add_event(session_id, Event(kind="screen", on_task=True, seen="from the other store"))
        assert len(first.events(session_id)) == 1

    def test_counts_reflect_what_is_on_disk(self, session):
        session._record(Event(kind="screen", on_task=True, seen="a"))
        session._record(Event(kind="screen", on_task=True, seen="b"))
        assert session.store.counts()["events"] == 2


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


# ── the intrusion policy ────────────────────────────────────────────────────


PAPER_CONTRACT = Contract(
    task="thermodynamics chapter 4 (entropy)",
    why="exam on Friday",
    artifacts=["notes.md"],
    signals=["screen", "camera", "diff"],
)


class TestShouldAskForNotes:
    """The camera is the only signal that costs the student something every time.

    So the rule is: never spend an interruption on something we already know. These
    pin that down, because it is the difference between a study companion and a
    tool that pesters you.
    """

    @pytest.fixture
    def paper_session(self, store, tmp_path):
        settings = Settings(db_path=tmp_path / "test.db", notes_prompt_every_min=25)
        return Session(MockProvider(), PAPER_CONTRACT, store=store, settings=settings)

    def test_not_asked_before_the_interval_has_passed(self, paper_session):
        assert paper_session.should_ask_for_notes() is False

    def test_asked_once_the_interval_has_passed(self, paper_session):
        paper_session.started_at = time.time() - 26 * 60
        assert paper_session.should_ask_for_notes() is True

    def test_never_asked_when_switched_off(self, paper_session):
        paper_session.started_at = time.time() - 60 * 60
        assert paper_session.should_ask_for_notes(every_min=0) is False

    def test_not_asked_when_the_file_already_proved_progress(self, paper_session):
        """The whole point: typing into a tracked file means no question."""
        paper_session.started_at = time.time() - 26 * 60
        paper_session._record(
            Event(kind="diff", seen="notes.md", detail={"verdict": "progress", "delta_words": 120})
        )
        assert paper_session.should_ask_for_notes() is False

    def test_still_asked_when_the_file_only_showed_padding(self, paper_session):
        # Padding is not evidence of work — this is exactly when a look at the page
        # earns its interruption.
        paper_session.started_at = time.time() - 26 * 60
        paper_session._record(Event(kind="diff", seen="notes.md", detail={"verdict": "padding"}))
        assert paper_session.should_ask_for_notes() is True

    def test_still_asked_when_the_file_is_stalled(self, paper_session):
        paper_session.started_at = time.time() - 26 * 60
        paper_session._record(Event(kind="diff", seen="notes.md", detail={"verdict": "stalled"}))
        assert paper_session.should_ask_for_notes() is True

    def test_never_asked_during_a_break(self, paper_session):
        paper_session.started_at = time.time() - 26 * 60
        paper_session.note_break(True)
        assert paper_session.should_ask_for_notes() is False
        paper_session.note_break(False)
        assert paper_session.should_ask_for_notes() is True

    def test_a_photo_resets_the_clock(self, paper_session):
        paper_session.started_at = time.time() - 26 * 60
        assert paper_session.should_ask_for_notes() is True
        paper_session._last_notes_check = time.time()
        assert paper_session.should_ask_for_notes() is False


class TestPaperNotes:
    def test_an_unreadable_photo_records_nothing(self, session, monkeypatch):
        """Holding a camera badly says nothing about whether they are working."""
        from heiddoon.core import notes as notes_mod
        from heiddoon.schemas import PageRead

        monkeypatch.setattr(
            notes_mod,
            "transcribe_page",
            lambda *a, **k: (PageRead(text="", legible=False), None),
        )
        page, diff = session.check_notes_photo(object())
        assert diff is None
        assert session.events == []  # nothing logged, focus score untouched

    def test_first_page_is_a_baseline_not_a_judgment(self, session, monkeypatch):
        from heiddoon.core import notes as notes_mod
        from heiddoon.schemas import PageRead

        monkeypatch.setattr(
            notes_mod,
            "transcribe_page",
            lambda *a, **k: (PageRead(text="entropy is a state function", legible=True), None),
        )
        page, diff = session.check_notes_photo(object())
        assert diff is None
        assert [event.kind for event in session.events] == ["notes"]
        assert session.events[0].detail["baseline"] is True

    def test_second_page_is_diffed_against_the_first(self, session, monkeypatch):
        from heiddoon.core import notes as notes_mod
        from heiddoon.schemas import PageRead

        pages = iter([
            "entropy is a state function",
            "entropy is a state function " + " ".join(f"w{n}" for n in range(40)),
        ])
        monkeypatch.setattr(
            notes_mod,
            "transcribe_page",
            lambda *a, **k: (PageRead(text=next(pages), legible=True), None),
        )
        session.check_notes_photo(object())
        page, diff = session.check_notes_photo(object())

        assert diff is not None
        assert diff.delta_words == 40  # counted from the transcriptions, not guessed
        diff_events = [event for event in session.events if event.kind == "diff"]
        assert diff_events[0].detail["source"] == "paper"

    def test_the_bouncer_can_see_a_photographed_page(self, session, monkeypatch):
        """The bug the user hit: a photographed page was invisible to the Bouncer.

        _artifact_text only looked at contract.artifacts, so the transcription sitting
        under the paper pseudo-path was ignored and the quiz was built from nothing.
        """
        from heiddoon.core import notes as notes_mod
        from heiddoon.schemas import PageRead

        written = "Entropy is a state function so only the endpoints matter, not the path taken."
        monkeypatch.setattr(
            notes_mod, "transcribe_page", lambda *a, **k: (PageRead(text=written, legible=True), None)
        )
        session.check_notes_photo(object())

        quiz = session.request_break()
        assert quiz.source == "your own notes"
        assert written[:30] in session.provider.calls[-1]

    def test_the_newest_source_wins(self, session, monkeypatch):
        """A page photographed after the last file save is the more current work."""
        from heiddoon.core import notes as notes_mod
        from heiddoon.schemas import PageRead

        session.store.add_snapshot(session.id, "notes.md", "older typed material about the Clausius inequality")
        monkeypatch.setattr(
            notes_mod,
            "transcribe_page",
            lambda *a, **k: (PageRead(text="newer handwritten material about free expansion", legible=True), None),
        )
        session.check_notes_photo(object())
        assert "newer handwritten" in session._artifact_text()

    def test_transcription_is_stored_under_a_pseudo_path(self, session, monkeypatch):
        """So a page can never collide with a real file on disk."""
        from heiddoon.core import notes as notes_mod
        from heiddoon.schemas import PageRead

        monkeypatch.setattr(
            notes_mod, "transcribe_page", lambda *a, **k: (PageRead(text="on paper", legible=True), None)
        )
        session.check_notes_photo(object())
        assert notes_mod.PAPER_PATH.startswith("paper:")
        assert session.store.latest_snapshot(session.id, notes_mod.PAPER_PATH)["content"] == "on paper"

    def test_illegible_flag_is_forced_false_when_there_is_no_text(self):
        from heiddoon.schemas import PageRead

        assert PageRead.from_model({"text": "", "legible": True}).legible is False


# ── the automatic loop ──────────────────────────────────────────────────────


class TestAutopilot:
    """An unchanged screen must not cost a model call.

    This is the difference between an affordable always-on watcher and one that
    spends a vision call every cadence to rediscover that the student is still on
    the same page of the same PDF.
    """

    def test_an_unchanged_screen_is_skipped_without_a_model_call(self, store, tmp_path, monkeypatch):
        import asyncio

        from PIL import Image

        from heiddoon.autopilot import Autopilot
        from heiddoon.watchers import screen as screen_mod

        still = Image.new("RGB", (200, 120), (240, 240, 240))
        monkeypatch.setattr(screen_mod, "available", lambda: True)
        monkeypatch.setattr(screen_mod, "capture", lambda *a, **k: still.copy())

        provider = MockProvider()
        settings = Settings(db_path=tmp_path / "test.db", notes_prompt_every_min=0)
        session = Session(provider, CONTRACT, store=store, settings=settings)

        async def run() -> None:
            autopilot = Autopilot(settings)
            await autopilot.start(session, cadence_s=1)
            await asyncio.sleep(3.4)
            await autopilot.stop(session.id)
            state = autopilot.state(session.id)
            # The first tick has nothing to compare against and is judged; every
            # tick after it sees the same screen and is skipped.
            assert state.checks == 1, f"expected one judged frame, got {state.checks}"
            assert state.skipped >= 1, "an unchanged screen was re-judged"

        asyncio.run(run())
        # One verdict call for the first frame, and nothing after it.
        assert len([call for call in provider.calls if "frame_kind" in call]) == 1
        assert len([event for event in session.events if event.kind == "screen"]) == 1

    def test_skips_are_not_logged_as_events(self, store, tmp_path, monkeypatch):
        """A log full of "unchanged" would bury the events that mean something."""
        import asyncio

        from PIL import Image

        from heiddoon.autopilot import Autopilot
        from heiddoon.watchers import screen as screen_mod

        still = Image.new("RGB", (200, 120), (10, 10, 10))
        monkeypatch.setattr(screen_mod, "available", lambda: True)
        monkeypatch.setattr(screen_mod, "capture", lambda *a, **k: still.copy())

        settings = Settings(db_path=tmp_path / "test.db", notes_prompt_every_min=0)
        session = Session(MockProvider(), CONTRACT, store=store, settings=settings)

        async def run() -> None:
            autopilot = Autopilot(settings)
            await autopilot.start(session, cadence_s=1)
            await asyncio.sleep(2.4)
            await autopilot.stop(session.id)

        asyncio.run(run())
        assert not [event for event in session.events if event.kind == "skip"]

    def test_start_reports_when_capture_is_unavailable(self, store, tmp_path, monkeypatch):
        import asyncio

        from heiddoon.autopilot import Autopilot
        from heiddoon.watchers import screen as screen_mod

        monkeypatch.setattr(screen_mod, "available", lambda: False)
        settings = Settings(db_path=tmp_path / "test.db")
        session = Session(MockProvider(), CONTRACT, store=store, settings=settings)

        async def run() -> None:
            autopilot = Autopilot(settings)
            state = await autopilot.start(session)
            assert state.running is False
            assert "mss" in state.last_error

        asyncio.run(run())


# ── screen capture ──────────────────────────────────────────────────────────


class TestScreenCapture:
    """The server can grab its own screen, but must say so rather than assume it.

    The browser's getDisplayMedia throws NotSupportedError in embedded webviews, so
    the server-side path is the primary one — which makes its availability check
    load-bearing for whether the UI offers the button at all.
    """

    def test_unavailable_without_mss(self, monkeypatch):
        from heiddoon.watchers import screen as screen_mod

        monkeypatch.setattr(screen_mod, "mss", None)
        assert screen_mod.available() is False

    def test_capture_raises_a_readable_error_without_mss(self, monkeypatch):
        from heiddoon.watchers import screen as screen_mod

        monkeypatch.setattr(screen_mod, "mss", None)
        with pytest.raises(screen_mod.ScreenUnavailable, match="pip install mss"):
            screen_mod.capture()

    def test_frame_hash_ignores_noise_but_catches_a_new_window(self):
        from PIL import Image

        from heiddoon.watchers import screen as screen_mod

        base = Image.new("RGB", (400, 300), (250, 250, 250))
        nudged = base.copy()
        nudged.putpixel((0, 0), (249, 249, 249))  # a cursor blink, effectively
        different = Image.new("RGB", (400, 300), (12, 40, 30))

        assert screen_mod.frame_hash(base) == screen_mod.frame_hash(nudged)
        assert screen_mod.frame_hash(base) != screen_mod.frame_hash(different)


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
