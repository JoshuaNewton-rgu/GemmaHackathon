"""F4's other half — watching the contracted file for changes.

The design doc called this the highest-value thing to build and it was never built:
the previous version could only diff two blobs of text handed to it. This is what
makes the work-diff a live signal instead of a demo — it notices when the student's
own file actually moves, and it waits for the writing to settle before judging so a
half-typed sentence is not called padding.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class _FileState:
    mtime: float = 0.0
    size: int = 0
    reported: bool = True


@dataclass
class ArtifactWatcher:
    """Polls the contracted files and reports one settled change at a time."""

    paths: list[str]
    settle_s: float = 5.0
    #: Never judge the same file more often than this, however much it is edited.
    min_interval_s: float = 300.0
    _states: dict[str, _FileState] = field(default_factory=dict, repr=False)
    _last_judged: dict[str, float] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # Record where every file starts, so the first real edit is a change rather
        # than being mistaken for one.
        for raw in self.paths:
            path = Path(raw).expanduser()
            state = _FileState()
            if path.is_file():
                stat = path.stat()
                state.mtime, state.size = stat.st_mtime, stat.st_size
            self._states[str(path)] = state

    def poll(self) -> list[str]:
        """Files that changed and have since stopped changing.

        Settling is measured from the file's own mtime rather than from the poll
        that noticed it. That way a file which finished being edited between two
        polls is judged on the next one instead of the one after, and the settle
        window means the same thing however irregular the polling is.
        """
        ready: list[str] = []
        now = time.time()

        for key, state in self._states.items():
            path = Path(key)
            if not path.is_file():
                continue
            stat = path.stat()
            if (stat.st_mtime, stat.st_size) != (state.mtime, state.size):
                state.mtime, state.size = stat.st_mtime, stat.st_size
                state.reported = False

            if state.reported:
                continue
            quiet_for = now - state.mtime
            if quiet_for < self.settle_s:
                continue  # still being written (or the clock disagrees with us)
            if now - self._last_judged.get(key, 0.0) < self.min_interval_s:
                continue  # judged recently; let some work accumulate

            state.reported = True
            self._last_judged[key] = now
            ready.append(key)

        return ready

    def read(self, path: str) -> str | None:
        target = Path(path).expanduser()
        if not target.is_file():
            return None
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def missing(self) -> list[str]:
        """Contracted files that do not exist — worth telling the student about."""
        return [key for key in self._states if not Path(key).is_file()]
