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


class Store:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or settings.db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
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
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO events (session_id, at, kind, on_task, seen, detail_json) VALUES (?, ?, ?, ?, ?, ?)",
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
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO snapshots (session_id, path, at, sha256, content) VALUES (?, ?, ?, ?, ?)",
                (session_id, path, time.time(), digest, content),
            )
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
