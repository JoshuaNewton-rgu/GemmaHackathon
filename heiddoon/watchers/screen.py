"""Screen capture, and a cheap way to tell whether anything changed.

The change hash matters more than it looks: a verdict costs seconds and, on a
hosted backend, money. If the screen is pixel-identical to the last check-in there
is nothing new to judge, so we skip the call and keep the previous verdict. On a
slow local model this is the difference between a usable watcher and one that is
permanently a minute behind.
"""

from __future__ import annotations

import hashlib
from typing import Any

try:
    import mss
except ImportError:  # pragma: no cover
    mss = None  # type: ignore[assignment]

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]


class ScreenUnavailable(RuntimeError):
    pass


def available() -> bool:
    return mss is not None and Image is not None


def capture(monitor: int = 1) -> Any:
    """Grab one frame of the given monitor as a PIL image."""
    if not available():
        raise ScreenUnavailable("screen capture needs: pip install mss pillow")
    with mss.mss() as capturer:
        monitors = capturer.monitors
        # monitors[0] is the union of all displays; 1..n are the individual ones.
        index = monitor if monitor < len(monitors) else 1
        shot = capturer.grab(monitors[index])
        return Image.frombytes("RGB", shot.size, shot.rgb)


def frame_hash(image: Any, grid: int = 32) -> str:
    """A hash that ignores noise but catches a new tab.

    Downscaling to a small greyscale grid before hashing means a blinking cursor,
    a clock tick or video compression noise does not read as "the screen changed",
    while switching windows always does.
    """
    if Image is None:  # pragma: no cover
        raise ScreenUnavailable("pillow is required")
    small = image.convert("L").resize((grid, grid))
    return hashlib.sha256(small.tobytes()).hexdigest()
