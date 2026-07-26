"""The automatic watch loop behind the web app.

Pressing a button to be watched is a chore, and a chore in a focus tool is a reason
to close the tab. This runs the screen check on a cadence instead, server-side, so
it keeps going while the student is in another window — which is the entire point,
since the interesting frames are the ones where the app is not in front.

Two economies matter, and they are the same economy: attention and money.

- An unchanged screen is skipped without a model call. A student reading one page of
  a PDF for ten minutes costs one verdict, not thirty. Perceptual hashing over a
  32×32 greyscale grid means a blinking cursor is not "a change" but a new tab is.
- Silence is the default output. A verdict that finds nothing wrong produces a log
  entry and nothing else — no notification, no sound, no badge.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from .config import Settings, settings as default_settings
from .core.session import Session
from .schemas import Event
from .watchers import artifact as artifact_mod, idle as idle_mod, screen as screen_mod


@dataclass
class AutopilotState:
    """What the UI needs to show about the loop, and what the loop needs to run."""

    running: bool = False
    #: True while a verdict is actually in flight. A vision call takes ~16s and
    #: cannot be made faster (thinking is mandatory on this model), so the UI needs
    #: to show that something is happening or the wait reads as a hang.
    busy: bool = False
    checks: int = 0
    skipped: int = 0
    last_check_at: float | None = None
    last_error: str = ""
    asked_for_notes_at: float | None = None
    _task: asyncio.Task | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "busy": self.busy,
            "checks": self.checks,
            "skipped_unchanged": self.skipped,
            "last_check_at": self.last_check_at,
            "last_error": self.last_error,
        }


class Autopilot:
    """Owns the background loops, one per session."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self._states: dict[int, AutopilotState] = {}

    def state(self, session_id: int) -> AutopilotState:
        return self._states.setdefault(session_id, AutopilotState())

    def is_running(self, session_id: int) -> bool:
        return self.state(session_id).running

    async def start(self, session: Session, *, cadence_s: int | None = None) -> AutopilotState:
        state = self.state(session.id)
        if state.running:
            return state
        if not screen_mod.available():
            state.last_error = "screen capture unavailable on the server: pip install mss"
            return state

        # Clamped: a demo wants this as low as it will go, but below a couple of
        # seconds the loop would spend its life capturing frames it has no time to
        # judge. The ceiling stops a typo parking the watcher for an afternoon.
        cadence = max(2, min(3600, cadence_s or self.settings.auto_cadence_s))
        state.running = True
        state.last_error = ""
        state._task = asyncio.create_task(self._loop(session, cadence, state))
        return state

    async def stop(self, session_id: int) -> None:
        state = self.state(session_id)
        state.running = False
        task = state._task
        state._task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def stop_all(self) -> None:
        for session_id in list(self._states):
            await self.stop(session_id)

    async def _loop(self, session: Session, cadence: int, state: AutopilotState) -> None:
        tracker = idle_mod.IdleTracker(threshold_s=cadence * 3)
        # Watching the file by mtime means an untouched file is never re-diffed, so
        # the only artifact checks that happen are ones with something to look at.
        watcher = artifact_mod.ArtifactWatcher(
            session.contract.artifacts if session.wants("diff") else [],
            settle_s=self.settings.artifact_settle_s,
        )
        last_hash: str | None = None

        try:
            while state.running:
                started = time.monotonic()
                try:
                    frame = await asyncio.to_thread(screen_mod.capture)
                    current_hash = await asyncio.to_thread(screen_mod.frame_hash, frame)
                    idle_s, unchanged = tracker.observe(current_hash)

                    if current_hash == last_hash:
                        # An identical screen produces an identical verdict, so
                        # judging it again buys nothing and costs a vision call.
                        #
                        # This skips regardless of whether the last verdict was good
                        # or bad, which is deliberate. Re-judging a *static off-task*
                        # screen would log a duplicate drift and fire the same nudge
                        # again every cadence — nagging, which is the behaviour this
                        # app exists to avoid. The drift is already on the record; if
                        # they have walked away, the idle signal is what notices.
                        #
                        # Nothing is logged for a skip either: a session log full of
                        # "unchanged" would bury the events that mean something.
                        state.skipped += 1
                    else:
                        state.busy = True
                        try:
                            await asyncio.to_thread(session.judge_frame, frame, kind="screen")
                        finally:
                            state.busy = False
                        state.checks += 1
                    last_hash = current_hash
                    state.last_check_at = time.time()
                    del frame  # the frame's life ends here, explicitly

                    if session.wants("idle"):
                        session.note_idle(idle_s, unchanged)

                    await self._check_changed_artifacts(session, watcher)
                    self._maybe_ask_for_notes(session, state)
                    state.last_error = ""
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - one bad tick must not end the session
                    state.last_error = f"{type(exc).__name__}: {exc}"

                elapsed = time.monotonic() - started
                await asyncio.sleep(max(1.0, cadence - elapsed))
        except asyncio.CancelledError:
            pass
        finally:
            state.running = False

    async def _check_changed_artifacts(self, session: Session, watcher: Any) -> None:
        """Diff the contracted file, but only once it has changed and settled.

        Polling mtime rather than diffing on a timer: a file nobody has touched has
        nothing to judge, and judging it anyway would spend a call to conclude
        "stalled" — which the student already knows.
        """
        for path in await asyncio.to_thread(watcher.poll):
            await asyncio.to_thread(session.check_artifact, path, against="latest")

    def _maybe_ask_for_notes(self, session: Session, state: AutopilotState) -> None:
        """Emit one soft request for a photo of the page, when it is fair to.

        The decision lives in Session.should_ask_for_notes; this only publishes it.
        An `ask_notes` event carries no verdict and no on_task value, so it cannot
        affect the focus score — being asked is not a mark against you, and neither
        is ignoring it.
        """
        if not session.wants("camera"):
            return
        if not session.should_ask_for_notes():
            return
        state.asked_for_notes_at = time.time()
        session._record(
            Event(
                kind="ask_notes",
                seen="show me the page",
                detail={
                    "prompt": "Whenever you get to a natural stop — hold your page up and I will "
                    "read where you are. Ignore this if you are mid-thought.",
                    "dismissable": True,
                },
            )
        )
