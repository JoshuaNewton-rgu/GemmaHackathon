from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from heiddoon.personas import PERSONAS, get_persona, resolve_persona_id, safe_feedback_text
from heiddoon.schemas import Contract, ProgressScore, StudyMetadata
from heiddoon.store import SCHEMA_VERSION, Store
from heiddoon.study import calculate_level, compute_progress_score, extract_concepts


def test_progress_score_is_bounded_and_components_add_up():
    score = compute_progress_score(
        elapsed_min=10_000,
        planned_duration_min=1,
        previous_text="",
        current_text=" ".join(f"concept{number}" for number in range(500)),
        diff_verdict="progress",
    )
    assert score.score == 100
    assert score.score == score.components.total
    assert 0 <= compute_progress_score(
        elapsed_min=-5, planned_duration_min=0, diff_verdict="unknown"
    ).score <= 100


def test_concepts_are_deterministic_and_include_phrases():
    text = "Entropy is a state function. A state function depends on endpoints."
    assert extract_concepts(text) == extract_concepts(text)
    assert "state function" in extract_concepts(text)


def test_levels_are_one_indexed():
    assert calculate_level(0) == 1
    assert calculate_level(99) == 1
    assert calculate_level(100) == 2


def test_study_duration_is_limited_to_five_through_120_minutes():
    assert StudyMetadata.from_dict({"planned_duration_min": 4}).planned_duration_min == 5
    assert StudyMetadata.from_dict({"planned_duration_min": 5}).planned_duration_min == 5
    assert StudyMetadata.from_dict({"planned_duration_min": 120}).planned_duration_min == 120
    assert StudyMetadata.from_dict({"planned_duration_min": 121}).planned_duration_min == 120


def test_optional_due_date_accepts_iso_dates_and_ignores_invalid_values():
    assert StudyMetadata.from_dict({"due_date": "2026-08-15"}).due_date == "2026-08-15"
    assert StudyMetadata.from_dict({"due_date": ""}).due_date == ""
    assert StudyMetadata.from_dict({"due_date": "next Friday"}).due_date == ""


def test_persona_registry_and_aliases_are_safe():
    assert set(PERSONAS) == {"scottish_granny", "disappointed_mother", "angry_father"}
    assert resolve_persona_id("kind_but_sharp") == "scottish_granny"
    assert resolve_persona_id("strict") == "angry_father"
    assert get_persona("unknown").id == "scottish_granny"
    assert "idiot" not in safe_feedback_text("You idiot!!!", "angry_father").lower()
    for persona in PERSONAS.values():
        assert 0.75 <= persona.tts_rate <= 1.25
        assert 0.8 <= persona.tts_pitch <= 1.2


def test_v2_database_migrates_without_losing_session(tmp_path):
    path = tmp_path / "v2.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile TEXT NOT NULL DEFAULT 'default',
            started_at REAL NOT NULL,
            ended_at REAL,
            contract_json TEXT NOT NULL,
            receipt_json TEXT
        );
        INSERT INTO sessions (profile, started_at, contract_json) VALUES ('default', 1.0, '{}');
        PRAGMA user_version = 2;
        """
    )
    connection.commit()
    connection.close()

    store = Store(path)
    metadata = store.get_study_metadata(1)
    assert metadata == StudyMetadata()
    check = sqlite3.connect(path)
    assert check.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert check.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    check.close()


def test_progress_round_trip(tmp_path):
    store = Store(tmp_path / "progress.db")
    session_id = store.start_session(
        Contract(),
        metadata=StudyMetadata(subject="Thermodynamics", due_date="2026-08-15"),
    )
    progress = ProgressScore(score=12)
    store.save_progress(session_id, progress)
    assert store.get_study_metadata(session_id).subject == "Thermodynamics"
    assert store.get_study_metadata(session_id).due_date == "2026-08-15"
    assert store.latest_progress(session_id).score == 12


def test_xp_is_idempotent_and_streak_rolls_on_utc_days(tmp_path):
    store = Store(tmp_path / "xp.db")
    first = store.start_session(Contract())
    second = store.start_session(Contract())
    third = store.start_session(Contract())

    day_one = datetime(2026, 7, 25, 23, 30, tzinfo=timezone.utc)
    state = store.award_session_xp(first, 70, now=day_one)
    assert (state.xp, state.streak_days) == (70, 1)
    assert store.award_session_xp(first, 70, now=day_one).xp == 70

    state = store.award_session_xp(second, 40, now=datetime(2026, 7, 26, 0, 5, tzinfo=timezone.utc))
    assert (state.xp, state.level, state.streak_days) == (110, 2, 2)

    state = store.award_session_xp(third, 10, now=datetime(2026, 7, 29, 12, tzinfo=timezone.utc))
    assert state.streak_days == 1


def test_quiz_models_reject_non_five_question_payloads():
    from heiddoon.schemas import QuizQuestion, QuizSet

    with pytest.raises(ValueError, match="exactly 5"):
        QuizSet(questions=[QuizQuestion(question="one")])
