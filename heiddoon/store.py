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
from pathlib import Path
from typing import Any, Iterator

from .config import settings
from .schemas import Contract, Event, LearnerModel, Receipt

#: Bumped when SCHEMA changes. Stored in the file's `user_version` so a connection
#: can tell an initialised database from an empty one.
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile       TEXT    NOT NULL DEFAULT 'default',
    started_at    REAL    NOT NULL,
    ended_at      REAL,
    contract_json TEXT    NOT NULL,
    receipt_json  TEXT
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

CREATE TABLE IF NOT EXISTS learner (
    profile    TEXT PRIMARY KEY,
    model_json TEXT NOT NULL,
    updated_at REAL NOT NULL
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
            if connection.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
                connection.executescript(SCHEMA)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            yield connection
            connection.commit()
        finally:
            connection.close()

    # ── sessions ────────────────────────────────────────────────────────────

    def start_session(self, contract: Contract, *, profile: str = "default") -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO sessions (profile, started_at, contract_json) VALUES (?, ?, ?)",
                (profile, time.time(), json.dumps(contract.to_dict())),
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
        }

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
        return {
            "sessions": int(sessions),
            "events": int(events),
            "snapshots": int(snapshots),
            "verdicts": int(verdicts),
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
