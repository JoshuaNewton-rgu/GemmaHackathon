"""Local SQLite persistence.

This file is why "adapt" is a real part of the loop rather than a slide. The
predecessor kept the learner model in a module-level dict, so every claim about
cross-session adaptation died with the process.

One rule holds throughout: **there is no column anywhere that can hold a frame.**
Screen and camera captures are judged in memory and dropped. What persists is the
verdict — what was seen, in words, and whether it was on task. Snapshots of the
contracted *artifact* are stored, because diffing needs a previous version, and the
student already owns that file.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import settings
from .personas import resolve_persona_id
from .schemas import (
    Contract,
    Event,
    GamificationState,
    LearnerModel,
    ProgressScore,
    QuizResult,
    QuizSet,
    Receipt,
    StudyMetadata,
)
from .study import calculate_level

#: Bumped when SCHEMA changes. Stored in the file's `user_version` so a connection
#: can tell an initialised database from an empty one.
SCHEMA_VERSION = 4  # 4 adds an optional study due date

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile       TEXT    NOT NULL DEFAULT 'default',
    started_at    REAL    NOT NULL,
    ended_at      REAL,
    contract_json TEXT    NOT NULL,
    receipt_json  TEXT,
    subject       TEXT    NOT NULL DEFAULT '',
    planned_duration_min INTEGER NOT NULL DEFAULT 25,
    persona_id    TEXT    NOT NULL DEFAULT 'scottish_granny',
    due_date      TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    at          REAL    NOT NULL,
    kind        TEXT    NOT NULL,
    on_task     INTEGER,
    seen        TEXT    NOT NULL DEFAULT '',
    detail_json TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS events_by_session ON events(session_id, at);

-- Snapshots of the student's own contracted file, for the work-diff. Never frames.
CREATE TABLE IF NOT EXISTS snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    path       TEXT    NOT NULL,
    at         REAL    NOT NULL,
    sha256     TEXT    NOT NULL,
    content    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS snapshots_by_path ON snapshots(session_id, path, at);

-- Tuned rule weights, per profile. Only weights and their history: the rules
-- themselves are code, so a stored file can never introduce a rule nobody reviewed.
CREATE TABLE IF NOT EXISTS rule_weights (
    profile    TEXT NOT NULL,
    rule_id    TEXT NOT NULL,
    weight     REAL NOT NULL,
    history    TEXT NOT NULL DEFAULT '[]',
    updated_at REAL NOT NULL,
    PRIMARY KEY (profile, rule_id)
);

CREATE TABLE IF NOT EXISTS learner (
    profile    TEXT PRIMARY KEY,
    model_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS study_progress (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    at            REAL    NOT NULL,
    progress_json TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS progress_by_session ON study_progress(session_id, at);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    at          REAL    NOT NULL,
    quiz_json   TEXT    NOT NULL,
    result_json TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS quizzes_by_session ON quiz_attempts(session_id, at);

CREATE TABLE IF NOT EXISTS gamification (
    profile         TEXT PRIMARY KEY,
    xp              INTEGER NOT NULL DEFAULT 0,
    level           INTEGER NOT NULL DEFAULT 1,
    streak_days     INTEGER NOT NULL DEFAULT 0,
    last_study_date TEXT,
    updated_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS session_xp (
    session_id INTEGER PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    profile    TEXT    NOT NULL,
    xp         INTEGER NOT NULL,
    awarded_at REAL    NOT NULL
);

-- A transcription of the latest paper notes, never the source photo.
CREATE TABLE IF NOT EXISTS paper_notes_profile (
    profile    TEXT PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    at         REAL NOT NULL,
    sha256     TEXT NOT NULL,
    content    TEXT NOT NULL
);
"""


class SessionGone(RuntimeError):
    """The session being written to no longer exists.

    Raised instead of leaking sqlite3.IntegrityError, which is what surfaced when
    the database was deleted mid-session: the schema is recreated on the next
    connection, but the session row is not, so every write failed the foreign key
    and returned a 500. The caller can recover from this; it cannot recover from a
    traceback.
    """


class Store:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or settings.db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Opening a connection is enough — `_connect` creates the schema when the
        # file does not already have it, and does so for every later connection too.
        with self._connect():
            pass

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            # Re-create the schema if this file does not have it. Creating tables
            # once in __init__ is not enough: sqlite3.connect() silently creates an
            # empty file, so if the database is deleted or moved while the app is
            # running — which happens, whether by tidying or by a sync client — the
            # next connection succeeds against an empty database and every write
            # then fails with "no such table: events" from deep inside a request.
            # `user_version` is a cheap, standard marker to detect that.
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version < SCHEMA_VERSION:
                connection.executescript(SCHEMA)
                if version < 3:
                    self._migrate_v3(connection)
                if version < 4:
                    self._migrate_v4(connection)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _migrate_v3(connection: sqlite3.Connection) -> None:
        """Add v3 session columns when opening a populated v2 database."""
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(sessions)").fetchall()}
        additions = {
            "subject": "TEXT NOT NULL DEFAULT ''",
            "planned_duration_min": "INTEGER NOT NULL DEFAULT 25",
            "persona_id": "TEXT NOT NULL DEFAULT 'scottish_granny'",
        }
        for name, declaration in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE sessions ADD COLUMN {name} {declaration}")

    @staticmethod
    def _migrate_v4(connection: sqlite3.Connection) -> None:
        """Add the optional due date without rebuilding existing databases."""
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(sessions)").fetchall()}
        if "due_date" not in columns:
            connection.execute("ALTER TABLE sessions ADD COLUMN due_date TEXT NOT NULL DEFAULT ''")

    # ── sessions ────────────────────────────────────────────────────────────

    def start_session(
        self,
        contract: Contract,
        *,
        profile: str = "default",
        study_metadata: StudyMetadata | None = None,
        metadata: StudyMetadata | None = None,
        subject: str = "",
        planned_duration_min: int = 25,
        persona_id: str = "scottish_granny",
    ) -> int:
        study = study_metadata or metadata or StudyMetadata(
            subject=subject,
            planned_duration_min=max(1, int(planned_duration_min)),
            persona_id=resolve_persona_id(persona_id),
        )
        study.persona_id = resolve_persona_id(study.persona_id)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO sessions "
                "(profile, started_at, contract_json, subject, planned_duration_min, persona_id, due_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    profile,
                    time.time(),
                    json.dumps(contract.to_dict()),
                    study.subject,
                    max(1, int(study.planned_duration_min)),
                    study.persona_id,
                    study.due_date,
                ),
            )
            return int(cursor.lastrowid)

    def end_session(self, session_id: int, receipt: Receipt | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET ended_at = ?, receipt_json = ? WHERE id = ?",
                (time.time(), json.dumps(receipt.to_dict()) if receipt else None, session_id),
            )

    def get_session(self, session_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "profile": row["profile"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "contract": json.loads(row["contract_json"]),
            "receipt": json.loads(row["receipt_json"]) if row["receipt_json"] else None,
            "study_metadata": {
                "subject": row["subject"],
                "planned_duration_min": row["planned_duration_min"],
                "persona_id": row["persona_id"],
                "due_date": row["due_date"],
            },
        }

    def save_study_metadata(self, session_id: int, metadata: StudyMetadata) -> None:
        persona_id = resolve_persona_id(metadata.persona_id)
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE sessions SET subject = ?, planned_duration_min = ?, persona_id = ?, due_date = ? "
                "WHERE id = ?",
                (
                    metadata.subject,
                    max(1, int(metadata.planned_duration_min)),
                    persona_id,
                    metadata.due_date,
                    session_id,
                ),
            )
            if cursor.rowcount == 0:
                raise SessionGone(f"session {session_id} no longer exists")

    set_study_metadata = save_study_metadata
    update_session_study_metadata = save_study_metadata

    def get_study_metadata(self, session_id: int) -> StudyMetadata | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT subject, planned_duration_min, persona_id, due_date FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return StudyMetadata(
            subject=row["subject"],
            planned_duration_min=row["planned_duration_min"],
            persona_id=resolve_persona_id(row["persona_id"]),
            due_date=row["due_date"],
        )

    def active_session_id(self, *, profile: str = "default") -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM sessions WHERE profile = ? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
                (profile,),
            ).fetchone()
        return int(row["id"]) if row else None

    def recent_sessions(self, *, profile: str = "default", limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, started_at, ended_at, receipt_json FROM sessions "
                "WHERE profile = ? ORDER BY started_at DESC LIMIT ?",
                (profile, limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "focus_score": (json.loads(row["receipt_json"]) or {}).get("focus_score")
                if row["receipt_json"]
                else None,
            }
            for row in rows
        ]

    # ── events ──────────────────────────────────────────────────────────────

    def add_event(self, session_id: int, event: Event) -> int:
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO events (session_id, at, kind, on_task, seen, detail_json) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        event.at,
                        event.kind,
                        None if event.on_task is None else int(event.on_task),
                        event.seen,
                        json.dumps(event.detail),
                    ),
                )
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise SessionGone(f"session {session_id} no longer exists") from exc

    def events(self, session_id: int) -> list[Event]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT at, kind, on_task, seen, detail_json FROM events WHERE session_id = ? ORDER BY at",
                (session_id,),
            ).fetchall()
        return [
            Event(
                kind=row["kind"],
                at=row["at"],
                on_task=None if row["on_task"] is None else bool(row["on_task"]),
                seen=row["seen"],
                detail=json.loads(row["detail_json"]),
            )
            for row in rows
        ]

    # ── artifact snapshots ──────────────────────────────────────────────────

    def add_snapshot(self, session_id: int, path: str, content: str) -> str:
        """Store a snapshot and return its hash. Identical content is not re-stored."""
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        latest = self.latest_snapshot(session_id, path)
        if latest and latest["sha256"] == digest:
            return digest
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO snapshots (session_id, path, at, sha256, content) VALUES (?, ?, ?, ?, ?)",
                    (session_id, path, time.time(), digest, content),
                )
        except sqlite3.IntegrityError as exc:
            raise SessionGone(f"session {session_id} no longer exists") from exc
        return digest

    def latest_snapshot(self, session_id: int, path: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT at, sha256, content FROM snapshots WHERE session_id = ? AND path = ? "
                "ORDER BY at DESC LIMIT 1",
                (session_id, path),
            ).fetchone()
        return {"at": row["at"], "sha256": row["sha256"], "content": row["content"]} if row else None

    def first_snapshot(self, session_id: int, path: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT at, sha256, content FROM snapshots WHERE session_id = ? AND path = ? "
                "ORDER BY at ASC LIMIT 1",
                (session_id, path),
            ).fetchone()
        return {"at": row["at"], "sha256": row["sha256"], "content": row["content"]} if row else None

    # ── ProofStudy progress and quizzes ─────────────────────────────────────

    def save_progress(self, session_id: int, progress: ProgressScore, *, at: float | None = None) -> int:
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO study_progress (session_id, at, progress_json) VALUES (?, ?, ?)",
                    (session_id, at if at is not None else time.time(), json.dumps(progress.to_dict())),
                )
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise SessionGone(f"session {session_id} no longer exists") from exc

    save_study_progress = save_progress
    record_progress = save_progress

    def progress_history(self, session_id: int) -> list[ProgressScore]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT progress_json FROM study_progress WHERE session_id = ? ORDER BY at, id",
                (session_id,),
            ).fetchall()
        return [ProgressScore.from_dict(json.loads(row["progress_json"])) for row in rows]

    def latest_progress(self, session_id: int) -> ProgressScore | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT progress_json FROM study_progress WHERE session_id = ? ORDER BY at DESC, id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        return ProgressScore.from_dict(json.loads(row["progress_json"])) if row else None

    get_progress = latest_progress

    def save_quiz_attempt(
        self,
        session_id: int,
        quiz: QuizSet,
        result: QuizResult,
        *,
        at: float | None = None,
    ) -> int:
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO quiz_attempts (session_id, at, quiz_json, result_json) VALUES (?, ?, ?, ?)",
                    (
                        session_id,
                        at if at is not None else time.time(),
                        json.dumps(quiz.to_dict()),
                        json.dumps(result.to_dict()),
                    ),
                )
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise SessionGone(f"session {session_id} no longer exists") from exc

    def quiz_attempts(self, session_id: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, at, quiz_json, result_json FROM quiz_attempts "
                "WHERE session_id = ? ORDER BY at, id",
                (session_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "at": row["at"],
                "quiz": QuizSet.from_dict(json.loads(row["quiz_json"])),
                "result": QuizResult.from_dict(json.loads(row["result_json"])),
            }
            for row in rows
        ]

    get_quiz_attempts = quiz_attempts
    record_quiz_attempt = save_quiz_attempt

    # ── profile continuity and gamification ─────────────────────────────────

    def save_paper_notes_snapshot(
        self,
        content: str,
        *,
        profile: str = "default",
        session_id: int | None = None,
        at: float | None = None,
    ) -> str:
        """Keep the latest transcription for the profile; never store an image."""
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO paper_notes_profile (profile, session_id, at, sha256, content) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(profile) DO UPDATE SET session_id = excluded.session_id, at = excluded.at, "
                "sha256 = excluded.sha256, content = excluded.content",
                (profile, session_id, at if at is not None else time.time(), digest, content),
            )
        return digest

    save_previous_paper_notes_snapshot = save_paper_notes_snapshot
    save_profile_paper_notes = save_paper_notes_snapshot

    def previous_paper_notes_snapshot(self, *, profile: str = "default") -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT session_id, at, sha256, content FROM paper_notes_profile WHERE profile = ?",
                (profile,),
            ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "at": row["at"],
            "sha256": row["sha256"],
            "content": row["content"],
        }

    get_previous_paper_notes_snapshot = previous_paper_notes_snapshot
    get_profile_paper_notes = previous_paper_notes_snapshot

    def get_gamification(self, *, profile: str = "default") -> GamificationState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT xp, level, streak_days, last_study_date FROM gamification WHERE profile = ?",
                (profile,),
            ).fetchone()
        if row is None:
            return GamificationState()
        return GamificationState(
            xp=row["xp"],
            level=row["level"],
            streak_days=row["streak_days"],
            last_study_date=row["last_study_date"],
        )

    def save_gamification(self, state: GamificationState, *, profile: str = "default") -> None:
        level = calculate_level(state.xp)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO gamification "
                "(profile, xp, level, streak_days, last_study_date, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(profile) DO UPDATE SET xp = excluded.xp, level = excluded.level, "
                "streak_days = excluded.streak_days, last_study_date = excluded.last_study_date, "
                "updated_at = excluded.updated_at",
                (
                    profile,
                    max(0, int(state.xp)),
                    level,
                    max(0, int(state.streak_days)),
                    state.last_study_date,
                    time.time(),
                ),
            )

    get_gamification_state = get_gamification
    save_gamification_state = save_gamification

    def award_session_xp(
        self,
        session_id: int,
        xp: int,
        *,
        profile: str | None = None,
        now: datetime | date | None = None,
    ) -> GamificationState:
        """Award XP once per session and roll the streak on UTC calendar days."""
        award = max(0, int(xp))
        if isinstance(now, datetime):
            current_date = (now if now.tzinfo else now.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).date()
        elif isinstance(now, date):
            current_date = now
        else:
            current_date = datetime.now(timezone.utc).date()

        with self._connect() as connection:
            session = connection.execute(
                "SELECT profile FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if session is None:
                raise SessionGone(f"session {session_id} no longer exists")
            selected_profile = profile or str(session["profile"])
            existing_award = connection.execute(
                "SELECT 1 FROM session_xp WHERE session_id = ?", (session_id,)
            ).fetchone()
            row = connection.execute(
                "SELECT xp, streak_days, last_study_date FROM gamification WHERE profile = ?",
                (selected_profile,),
            ).fetchone()
            current_xp = int(row["xp"]) if row else 0
            streak = int(row["streak_days"]) if row else 0
            last_date = date.fromisoformat(row["last_study_date"]) if row and row["last_study_date"] else None

            if existing_award is None:
                current_xp += award
                if last_date is None:
                    streak = 1
                elif current_date == last_date:
                    pass
                elif (current_date - last_date).days == 1:
                    streak += 1
                elif current_date > last_date:
                    streak = 1
                connection.execute(
                    "INSERT INTO session_xp (session_id, profile, xp, awarded_at) VALUES (?, ?, ?, ?)",
                    (session_id, selected_profile, award, time.time()),
                )
                last_date = current_date if last_date is None or current_date >= last_date else last_date
                connection.execute(
                    "INSERT INTO gamification "
                    "(profile, xp, level, streak_days, last_study_date, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(profile) DO UPDATE SET xp = excluded.xp, level = excluded.level, "
                    "streak_days = excluded.streak_days, last_study_date = excluded.last_study_date, "
                    "updated_at = excluded.updated_at",
                    (
                        selected_profile,
                        current_xp,
                        calculate_level(current_xp),
                        streak,
                        last_date.isoformat() if last_date else None,
                        time.time(),
                    ),
                )

        return self.get_gamification(profile=selected_profile)

    # ── learner model ───────────────────────────────────────────────────────

    def get_learner(self, *, profile: str = "default") -> LearnerModel:
        with self._connect() as connection:
            row = connection.execute("SELECT model_json FROM learner WHERE profile = ?", (profile,)).fetchone()
        if row is None:
            return LearnerModel()
        return LearnerModel.from_model(json.loads(row["model_json"]))

    def save_learner(self, learner: LearnerModel, *, profile: str = "default") -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO learner (profile, model_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(profile) DO UPDATE SET model_json = excluded.model_json, "
                "updated_at = excluded.updated_at",
                (profile, json.dumps(learner.to_dict()), time.time()),
            )

    # ── tuned rule weights ──────────────────────────────────────────────────

    def get_rule_weights(self, *, profile: str = "default") -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT rule_id, weight, history FROM rule_weights WHERE profile = ?", (profile,)
            ).fetchall()
        return {
            row["rule_id"]: {"weight": row["weight"], "history": json.loads(row["history"])}
            for row in rows
        }

    def save_rule_weight(
        self, rule_id: str, weight: float, history: list[str], *, profile: str = "default"
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO rule_weights (profile, rule_id, weight, history, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(profile, rule_id) DO UPDATE SET "
                "weight = excluded.weight, history = excluded.history, updated_at = excluded.updated_at",
                (profile, rule_id, float(weight), json.dumps(history), time.time()),
            )

    def reset_rule_weights(self, *, profile: str = "default") -> int:
        """Back to the shipped defaults. A tuned system must be un-tunable too."""
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM rule_weights WHERE profile = ?", (profile,))
            return cursor.rowcount

    # ── the student's data is the student's ─────────────────────────────────
    # "Monitoring you opted into" only means anything if you can also see all of
    # it and take it away. Both of these are part of the product, not admin tools.

    def recent_verdicts(self, *, profile: str = "default", limit: int = 3) -> list[dict[str, Any]]:
        """The latest frame verdicts, for the privacy screen's log.

        Shows the student exactly what was retained from looking at their screen:
        a sentence, and nothing else.
        """
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT e.at, e.kind, e.on_task, e.seen FROM events e JOIN sessions s ON s.id = e.session_id "
                "WHERE s.profile = ? AND e.kind IN ('screen', 'camera') ORDER BY e.at DESC LIMIT ?",
                (profile, limit),
            ).fetchall()
        return [
            {
                "at": row["at"],
                "kind": row["kind"],
                "on_task": None if row["on_task"] is None else bool(row["on_task"]),
                "seen": row["seen"],
            }
            for row in rows
        ]

    def counts(self, *, profile: str = "default") -> dict[str, int]:
        """What is actually on disk, for an honest privacy screen."""
        with self._connect() as connection:
            sessions = connection.execute(
                "SELECT COUNT(*) AS n FROM sessions WHERE profile = ?", (profile,)
            ).fetchone()["n"]
            events = connection.execute(
                "SELECT COUNT(*) AS n FROM events e JOIN sessions s ON s.id = e.session_id WHERE s.profile = ?",
                (profile,),
            ).fetchone()["n"]
            snapshots = connection.execute(
                "SELECT COUNT(*) AS n FROM snapshots p JOIN sessions s ON s.id = p.session_id "
                "WHERE s.profile = ?",
                (profile,),
            ).fetchone()["n"]
            # Counted separately from `events`: a frame verdict is the thing a
            # student wants a number for on the privacy screen, and calling the
            # diffs and quizzes "verdicts" there would overstate what was watched.
            verdicts = connection.execute(
                "SELECT COUNT(*) AS n FROM events e JOIN sessions s ON s.id = e.session_id "
                "WHERE s.profile = ? AND e.kind IN ('screen', 'camera')",
                (profile,),
            ).fetchone()["n"]
            # Excerpts read off the screen are counted apart from file snapshots:
            # the student chose to have a file tracked, but work read from whatever
            # happened to be on screen is a different kind of keeping, and the
            # privacy screen has to say so in its own words.
            excerpts = connection.execute(
                "SELECT COUNT(*) AS n FROM snapshots p JOIN sessions s ON s.id = p.session_id "
                "WHERE s.profile = ? AND p.path LIKE 'screen:%'",
                (profile,),
            ).fetchone()["n"]
        return {
            "sessions": int(sessions),
            "events": int(events),
            "snapshots": int(snapshots),
            "verdicts": int(verdicts),
            "screen_excerpts": int(excerpts),
        }

    def export_all(self, *, profile: str = "default") -> dict[str, Any]:
        """Everything held about this student, in one JSON-serialisable object.

        Note what cannot appear here however hard you look: a frame. Snapshots of
        the contracted file are included because they are the student's own
        writing and they asked for their data.
        """
        with self._connect() as connection:
            sessions = connection.execute(
                "SELECT * FROM sessions WHERE profile = ? ORDER BY started_at", (profile,)
            ).fetchall()
            session_ids = [row["id"] for row in sessions]
            events = (
                connection.execute(
                    f"SELECT * FROM events WHERE session_id IN ({','.join('?' * len(session_ids))}) ORDER BY at",
                    session_ids,
                ).fetchall()
                if session_ids
                else []
            )
            snapshots = (
                connection.execute(
                    f"SELECT id, session_id, path, at, sha256, content FROM snapshots "
                    f"WHERE session_id IN ({','.join('?' * len(session_ids))}) ORDER BY at",
                    session_ids,
                ).fetchall()
                if session_ids
                else []
            )

        return {
            "exported_at": time.time(),
            "profile": profile,
            "note": "Verdicts, note snapshots and the learner model. No frame is stored by Heid Doon.",
            "learner_model": self.get_learner(profile=profile).to_dict(),
            "sessions": [
                {
                    "id": row["id"],
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "contract": json.loads(row["contract_json"]),
                    "receipt": json.loads(row["receipt_json"]) if row["receipt_json"] else None,
                }
                for row in sessions
            ],
            "events": [
                {
                    "session_id": row["session_id"],
                    "at": row["at"],
                    "kind": row["kind"],
                    "on_task": None if row["on_task"] is None else bool(row["on_task"]),
                    "seen": row["seen"],
                    "detail": json.loads(row["detail_json"]),
                }
                for row in events
            ],
            "artifact_snapshots": [
                {
                    "session_id": row["session_id"],
                    "path": row["path"],
                    "at": row["at"],
                    "sha256": row["sha256"],
                    "content": row["content"],
                }
                for row in snapshots
            ],
        }

    def delete_all(self, *, profile: str = "default") -> dict[str, int]:
        """Erase everything for this profile. Returns what was removed.

        No soft delete, no tombstones, no "archived" flag. The student was told
        they could delete it, so it is gone.
        """
        removed = self.counts(profile=profile)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM events WHERE session_id IN (SELECT id FROM sessions WHERE profile = ?)",
                (profile,),
            )
            connection.execute(
                "DELETE FROM snapshots WHERE session_id IN (SELECT id FROM sessions WHERE profile = ?)",
                (profile,),
            )
            connection.execute("DELETE FROM sessions WHERE profile = ?", (profile,))
            connection.execute("DELETE FROM learner WHERE profile = ?", (profile,))
            connection.execute("DELETE FROM rule_weights WHERE profile = ?", (profile,))
            connection.execute("DELETE FROM gamification WHERE profile = ?", (profile,))
            connection.execute("DELETE FROM paper_notes_profile WHERE profile = ?", (profile,))

        # VACUUM cannot run inside a transaction, and sqlite3 opens one implicitly
        # for the DELETEs above — so it gets its own autocommit connection. Worth
        # doing rather than skipping: without it the deleted rows stay legible in
        # the file's free pages, and "delete everything" should mean it.
        vacuum = sqlite3.connect(self.path, isolation_level=None)
        try:
            vacuum.execute("VACUUM")
        finally:
            vacuum.close()
        return removed
