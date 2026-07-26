"""How long since the student last touched the machine.

The cheapest signal in the product and the only one that needs no model at all.
Combined with an unchanged screen it answers a question neither the screen nor the
camera can: they are not here. Costs nothing, so it runs every check-in.
"""

from __future__ import annotations

import ctypes
import sys
import time


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_ulong)]


def available() -> bool:
    return sys.platform == "win32"


def idle_seconds() -> int:
    """Seconds since the last keyboard or mouse input.

    Windows only for now. Elsewhere this returns 0, which means "assume they are
    here" — the safe direction, since the alternative is accusing someone of
    absence because we could not measure it.
    """
    if sys.platform != "win32":
        return 0
    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):  # type: ignore[attr-defined]
        return 0
    ticks = ctypes.windll.kernel32.GetTickCount()  # type: ignore[attr-defined]
    # GetTickCount wraps roughly every 49 days; treat a wrap as "not idle".
    elapsed_ms = ticks - info.dwTime
    return max(0, elapsed_ms // 1000) if elapsed_ms >= 0 else 0


class IdleTracker:
    """Tracks idle time and screen stillness together."""

    def __init__(self, threshold_s: int) -> None:
        self.threshold_s = threshold_s
        self._last_hash: str | None = None
        self._unchanged_since: float | None = None

    def observe(self, frame_hash: str) -> tuple[int, bool]:
        """Feed the latest screen hash; get back (idle seconds, screen unchanged)."""
        now = time.time()
        if frame_hash != self._last_hash:
            self._last_hash = frame_hash
            self._unchanged_since = now
            return idle_seconds(), False
        unchanged_for = now - (self._unchanged_since or now)
        return idle_seconds(), unchanged_for >= self.threshold_s
