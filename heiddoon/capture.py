"""Capturing the real frames the eval needs.

The test set shipped as rendered mock-ups, which the model reads as text — so they
score near-perfectly and measure nothing. Replacing them is the single highest-value
task on the list, and it is pure manual labour: open a real page, screenshot it,
name the file correctly, repeat twelve times.

This turns each one into one command with a countdown, so the whole set takes a few
minutes instead of half an hour, and the filenames always match the labels.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def load_labels(testset: Path) -> dict[str, dict[str, Any]]:
    labels = json.loads((testset / "labels.json").read_text(encoding="utf-8"))
    return {name: meta for name, meta in labels.items() if not name.startswith("_")}


def status(testset: Path) -> tuple[list[str], list[str]]:
    """(captured, still missing) among the frames labelled as real."""
    labels = load_labels(testset)
    real = [name for name, meta in labels.items() if meta.get("source") == "real"]
    captured = [name for name in real if (testset / name).exists()]
    missing = [name for name in real if not (testset / name).exists()]
    return captured, missing


def print_status(testset: Path) -> None:
    labels = load_labels(testset)
    captured, missing = status(testset)

    print(f"\nreal frames: {len(captured)} captured, {len(missing)} to go")
    if captured:
        print("\n  done:")
        for name in captured:
            print(f"    ✓ {name}")
    if missing:
        print("\n  still needed:")
        for name in missing:
            meta = labels[name]
            expected = "ON task" if meta["on_task"] else "OFF task"
            hint = str(meta.get("note", "")).removeprefix("CAPTURE: ")
            print(f"    · {name:28} [{meta['kind']:6} · {expected:8}] {hint}")
        print(f"\n  capture the next one with:\n    python -m heiddoon capture {missing[0]}")
    else:
        print("\n  all real frames captured — run: python -m heiddoon eval")


def capture_frame(
    name: str,
    testset: Path,
    *,
    delay: int = 8,
    camera: bool = False,
    verify: bool = True,
) -> int:
    """Count down, grab a frame, save it under the labelled filename, describe it.

    The describe step is not a nicety. The first real capture taken with this
    command grabbed the editor window it was typed into rather than the intended
    lecture page, and the label said "lecture video" — so the eval scored a false
    accusation against the model for a frame that was simply the wrong screenshot.
    A mislabelled frame is worse than a missing one: missing frames are counted and
    reported, wrong ones quietly corrupt the number. One extra call catches it while
    you are still sitting there.
    """
    labels = load_labels(testset)
    meta = labels.get(name)
    if meta is None:
        # Accept a partial name so the whole filename need not be typed.
        matches = [key for key in labels if name.lower() in key.lower()]
        if len(matches) == 1:
            name, meta = matches[0], labels[matches[0]]
        elif matches:
            print(f"{name!r} matches several labels: {matches}")
            return 1
        else:
            print(f"{name!r} is not in labels.json. Run `python -m heiddoon capture --list`.")
            return 1

    if meta.get("source") != "real":
        print(f"{name} is labelled source={meta.get('source')!r}, not 'real' — nothing to capture.")
        return 1

    is_camera = camera or meta.get("kind") == "camera"
    expected = "ON task" if meta["on_task"] else "OFF task"
    print(f"\n{name}")
    print(f"  {meta['kind']} frame, labelled {expected} ({meta.get('case')} case)")
    print(f"  {str(meta.get('note', '')).removeprefix('CAPTURE: ')}")
    print()

    if is_camera:
        from .watchers import camera as camera_mod

        if not camera_mod.available():
            print("  webcam capture needs: pip install opencv-python")
            return 1
    else:
        from .watchers import screen as screen_mod

        if not screen_mod.available():
            print("  screen capture needs: pip install mss")
            return 1

    if is_camera:
        print("  get into position — the camera light will come on once.")
    else:
        print("  SWITCH NOW to the window you want captured. This grabs the whole screen,")
        print("  so whatever is in front when the countdown ends is what gets scored.")
    print()

    for remaining in range(delay, 0, -1):
        print(f"  capturing in {remaining}…  ", end="\r", flush=True)
        time.sleep(1)

    if is_camera:
        from .watchers import camera as camera_mod

        frame = camera_mod.capture()
    else:
        from .watchers import screen as screen_mod

        frame = screen_mod.capture()

    path = testset / name
    if path.suffix.lower() in (".jpg", ".jpeg"):
        frame.save(path, "JPEG", quality=90)
    else:
        frame.save(path, "PNG")

    print(f"  saved {path}  ({frame.width}×{frame.height})            ")

    if verify:
        described = _describe(frame)
        if described:
            print(f"\n  the model sees: {described}")
            print(f"  labelled as:    {expected}, {str(meta.get('note', '')).removeprefix('CAPTURE: ')}")
            print("\n  If that description is not what you meant to capture, run the same")
            print("  command again — it overwrites.")

    print_status(testset)
    return 0


def _describe(frame: Any) -> str:
    """One cheap call: what did we actually just capture?

    Failures here are printed and ignored — a verification step must never be the
    reason a capture is lost.
    """
    try:
        from .providers import get_provider

        provider = get_provider()
        payload, meta = provider.complete_json(
            'Describe what is on this screen in one short sentence. Schema: {"seen": str}',
            image=frame,
            max_tokens=150,
        )
        if not meta.ok:
            return f"(could not check: {meta.error})"
        return str(payload.get("seen", "")).strip()
    except Exception as exc:  # noqa: BLE001 - never lose a capture over this
        return f"(could not check: {exc})"
