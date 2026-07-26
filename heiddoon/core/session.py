"""The loop, assembled.

Contract → Watch → Intervene → Negotiate → Checkpoint → Receipt → Adapt.

The mechanics each work in isolation; this is the object that makes them one
product. Everything that happens goes through here, so there is exactly one place
that writes to the event log — which is what makes the receipt an account of what
actually happened rather than a plausible story about it.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from ..config import Settings, settings as default_settings
from ..providers import Provider
from ..schemas import Contract, Diff, Event, Grade, PageRead, Quiz, Receipt, Verdict
from ..store import Store
from . import (
    bouncer,
    diff as diff_mod,
    notes as notes_mod,
    receipt as receipt_mod,
    verdict as verdict_mod,
)

Listener = Callable[[Event], None]


class Session:
    """One study session, persisted as it goes."""

    def __init__(
        self,
        provider: Provider,
        contract: Contract,
        *,
        store: Store | None = None,
        settings: Settings | None = None,
        profile: str = "default",
        session_id: int | None = None,
    ) -> None:
        self.provider = provider
        self.contract = contract
        self.settings = settings or default_settings
        self.store = store or Store(self.settings.db_path)
        self.profile = profile
        self.started_at = time.time()
        self.id = session_id if session_id is not None else self.store.start_session(contract, profile=profile)
        self.learner = self.store.get_learner(profile=profile)
        self._listeners: list[Listener] = []
        self._pending_quiz: Quiz | None = None
        self._last_artifact_check: dict[str, float] = {}
        self._last_notes_check: float | None = None
        self._on_break = False

    # ── plumbing ────────────────────────────────────────────────────────────

    def on_event(self, listener: Listener) -> None:
        """Subscribe to events as they are recorded (used by the web UI stream)."""
        self._listeners.append(listener)

    def _record(self, event: Event) -> Event:
        self.store.add_event(self.id, event)
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:  # noqa: BLE001 - a broken listener must not end a session
                pass
        return event

    @property
    def events(self) -> list[Event]:
        return self.store.events(self.id)

    @property
    def elapsed_min(self) -> int:
        return int((time.time() - self.started_at) // 60)

    def wants(self, signal: str) -> bool:
        return signal in self.contract.signals

    # ── watch + intervene ───────────────────────────────────────────────────

    def judge_frame(self, image: Any, *, kind: str = "screen") -> Verdict:
        """Judge a frame and log the verdict. The frame itself is never stored."""
        result, _ = verdict_mod.judge_frame(self.provider, self.contract, image, expect_kind=kind)
        self._record(
            Event(
                kind=kind,
                on_task=result.on_task,
                seen=result.seen,
                detail={
                    "reason": result.reason,
                    "nudge": result.nudge,
                    "confidence": result.confidence,
                    "latency_s": result._meta.get("latency_s"),
                },
            )
        )
        return result

    def note_idle(self, idle_s: int, screen_unchanged: bool) -> Event | None:
        """F10 — cheap signal: an unchanged screen plus no input means you are elsewhere.

        Costs nothing and catches the case the camera and the screen both miss:
        the student is not at the machine at all. No model call — there is nothing
        to interpret, and spending twenty seconds of inference to conclude "the
        screen did not change" would be absurd.
        """
        if not (screen_unchanged and idle_s >= self.settings.cadence_s * 3):
            return None
        return self._record(
            Event(
                kind="idle",
                on_task=False,
                seen=f"no input for {idle_s // 60}m {idle_s % 60}s, screen unchanged",
                detail={"idle_s": idle_s, "nudge": verdict_mod._fallback_nudge(self.contract)},
            )
        )

    # ── the work-diff ───────────────────────────────────────────────────────

    def snapshot_artifacts(self) -> list[str]:
        """Record the current contents of every contracted file that exists."""
        recorded = []
        for artifact in self.contract.artifacts:
            path = Path(artifact).expanduser()
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            self.store.add_snapshot(self.id, str(path), content)
            recorded.append(str(path))
        return recorded

    def check_artifact(self, artifact: str, *, against: str = "session_start") -> Diff | None:
        """Judge the contracted file's delta and log it.

        `against="session_start"` compares with the first snapshot of the session,
        which is the number the student cares about — "what did I get done in this
        hour" — rather than the last twenty minutes in isolation.
        """
        path = Path(artifact).expanduser()
        if not path.is_file():
            return None
        try:
            current = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        baseline = (
            self.store.first_snapshot(self.id, str(path))
            if against == "session_start"
            else self.store.latest_snapshot(self.id, str(path))
        )
        self.store.add_snapshot(self.id, str(path), current)

        if baseline is None:
            # Nothing to compare against yet; this call established the baseline.
            return None

        minutes = max(1, int((time.time() - baseline["at"]) // 60))
        result, _ = diff_mod.judge_delta(
            self.provider, self.contract, baseline["content"], current, minutes=minutes
        )
        self._last_artifact_check[str(path)] = time.time()
        self._record(
            Event(
                kind="diff",
                seen=path.name,
                detail={
                    "verdict": result.verdict,
                    "delta_words": result.delta_words,
                    "summary": result.summary,
                    "quality_note": result.quality_note,
                    "minutes": minutes,
                },
            )
        )
        return result

    # ── handwritten notes ───────────────────────────────────────────────────

    def check_notes_photo(self, image: Any) -> tuple[PageRead, Diff | None]:
        """Read a photo of a paper page and judge it as a delta.

        Returns the transcription and, if there is a previous page to compare with,
        the diff. The first photo of a session establishes the baseline and is not
        a judgment — nobody should be told their notes are "stalled" because we have
        only seen them once.
        """
        page, _ = notes_mod.transcribe_page(self.provider, self.contract, image)
        self._last_notes_check = time.time()

        if notes_mod.unreadable_reason(page) is not None:
            # An unusable photo is not an event. It says nothing about their work,
            # and logging it would drag the focus score down for holding a camera
            # badly.
            return page, None

        baseline = self.store.latest_snapshot(self.id, notes_mod.PAPER_PATH)
        self.store.add_snapshot(self.id, notes_mod.PAPER_PATH, page.text)

        if baseline is None:
            self._record(
                Event(
                    kind="notes",
                    on_task=True,
                    seen=page.page_note or "a page of notes",
                    detail={"baseline": True, "words": diff_mod.count_words(page.text)},
                )
            )
            return page, None

        minutes = max(1, int((time.time() - baseline["at"]) // 60))
        result, _ = diff_mod.judge_delta(
            self.provider, self.contract, baseline["content"], page.text, minutes=minutes
        )
        self._record(
            Event(
                kind="diff",
                seen=page.page_note or "paper notes",
                detail={
                    "verdict": result.verdict,
                    "delta_words": result.delta_words,
                    "summary": result.summary,
                    "quality_note": result.quality_note,
                    "minutes": minutes,
                    "source": "paper",
                },
            )
        )
        return page, result

    def should_ask_for_notes(self, *, every_min: int | None = None) -> bool:
        """Whether it is fair to interrupt and ask for a photo of the page.

        The whole intrusion policy lives here, because the camera is the only signal
        that costs the student something every time it fires. Four conditions, all
        of which must hold:

        - asking is switched on at all;
        - enough time has passed since the last photo, or since the session began;
        - the screen has not already proved they are working — a tracked file that
          moved, or a page photo, is evidence, and evidence means no question;
        - they are not currently on a break.

        The third condition is the important one. A student typing into their
        contracted file should never be asked to show anything, because the diff has
        already answered it.
        """
        interval = self.settings.notes_prompt_every_min if every_min is None else every_min
        if interval <= 0:
            return False
        if self._on_break:
            return False

        since = time.time() - (self._last_notes_check or self.started_at)
        if since < interval * 60:
            return False

        # Any progress evidence inside the window means we are not blind, so we keep
        # quiet. Padding and stalled do not count as evidence — those are exactly
        # the cases where a look at the page is worth the interruption.
        window_start = time.time() - interval * 60
        for event in self.events:
            if event.kind == "diff" and event.at >= window_start:
                if event.detail.get("verdict") == "progress":
                    return False
        return True

    def note_break(self, on_break: bool) -> None:
        """Breaks suspend the ask — an earned break should be undisturbed."""
        self._on_break = on_break

    def judge_text_delta(self, before: str, after: str, *, minutes: int = 20) -> Diff:
        """Judge a delta supplied directly — how the web UI's diff tab works."""
        result, _ = diff_mod.judge_delta(self.provider, self.contract, before, after, minutes=minutes)
        self._record(
            Event(
                kind="diff",
                seen="pasted notes",
                detail={
                    "verdict": result.verdict,
                    "delta_words": result.delta_words,
                    "summary": result.summary,
                    "quality_note": result.quality_note,
                    "minutes": minutes,
                },
            )
        )
        return result

    # ── negotiate ───────────────────────────────────────────────────────────

    def request_break(self, notes: str | None = None) -> Quiz:
        """Ask the Bouncer for a break: it asks one question back."""
        source = notes if notes is not None else self._artifact_text()
        quiz, _ = bouncer.ask_question(self.provider, source or "")
        self._pending_quiz = quiz
        return quiz

    def answer_break(self, answer: str, *, quiz: Quiz | None = None) -> Grade:
        target = quiz or self._pending_quiz
        if target is None:
            return Grade(passed=False, feedback="Ask for a break first and I will ask you something.")
        grade, _ = bouncer.grade_answer(self.provider, target, answer)
        self._record(
            Event(
                kind="quiz",
                on_task=True,
                seen=target.question,
                detail={"pass": grade.passed, "feedback": grade.feedback},
            )
        )
        if grade.passed:
            self._pending_quiz = None
        return grade

    def _artifact_text(self) -> str:
        """The most recent snapshot of the contracted file, for quiz generation."""
        for artifact in self.contract.artifacts:
            snapshot = self.store.latest_snapshot(self.id, str(Path(artifact).expanduser()))
            if snapshot:
                return snapshot["content"]
        return ""

    # ── receipt + adapt ─────────────────────────────────────────────────────

    def finish(self) -> Receipt:
        """End the session: autopsy, updated learner model, tomorrow's shape.

        The learner model is saved *before* the session is closed, so a crash while
        writing the receipt still leaves what was learned intact.
        """
        result, _ = receipt_mod.make_receipt(
            self.provider, self.events, self.learner, session_start=self.started_at
        )
        self.learner = result.learner_model
        self.store.save_learner(self.learner, profile=self.profile)
        self.store.end_session(self.id, result)
        return result

    # ── resume ──────────────────────────────────────────────────────────────

    @classmethod
    def resume(
        cls,
        provider: Provider,
        session_id: int,
        *,
        store: Store | None = None,
        settings: Settings | None = None,
    ) -> Session:
        """Reattach to a session already in the database.

        Needed because the watcher process and the web UI are separate programs
        looking at the same session.
        """
        config = settings or default_settings
        active_store = store or Store(config.db_path)
        record = active_store.get_session(session_id)
        if record is None:
            raise ValueError(f"no session {session_id}")
        session = cls(
            provider,
            Contract.from_model(record["contract"]),
            store=active_store,
            settings=config,
            profile=record["profile"],
            session_id=session_id,
        )
        session.started_at = record["started_at"]
        return session
