"""Webcam frames — the presence signal.

Catches what the screen cannot: a phone in your hand, or nobody in the chair. The
camera is opened for a single frame and released immediately, every time. That is
slower than holding the device open, and it is the right trade: an app that keeps a
webcam handle open for an hour is one the student has to take on trust, and the
camera light going on and off at the check-in cadence is a visible, honest signal of
exactly when it looked.
"""

from __future__ import annotations

from typing import Any

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]


class CameraUnavailable(RuntimeError):
    pass


def available() -> bool:
    return cv2 is not None and Image is not None


def capture(device: int = 0, *, warmup_frames: int = 3) -> Any:
    """One frame from the webcam, as a PIL image.

    The first frames out of a just-opened camera are usually black or badly
    exposed while auto-exposure settles, and a black frame reads to the model as
    an empty chair — a false accusation. So we throw a few away.
    """
    if not available():
        raise CameraUnavailable("webcam frames need: pip install opencv-python pillow")

    capturer = cv2.VideoCapture(device)
    try:
        if not capturer.isOpened():
            raise CameraUnavailable(f"could not open camera device {device}")
        frame = None
        for _ in range(max(1, warmup_frames)):
            ok, candidate = capturer.read()
            if ok:
                frame = candidate
        if frame is None:
            raise CameraUnavailable("camera opened but returned no frames")
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        capturer.release()
