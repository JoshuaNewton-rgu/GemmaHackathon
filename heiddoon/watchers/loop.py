"""The live watcher: the four signals, on a rhythm, feeding one session.

Twenty seconds between check-ins is a design choice before it is a budget — the app
is a study partner glancing over, not a keylogger. It also happens to be roughly
what a small local model can sustain.

What this process never does: write a frame anywhere. Screen and camera captures
exist as Python objects for the length of one judgment and are then unreferenced.
The only things that leave this function are verdicts, in words.
"""

from __future__ import annotations

import time
from pathlib import Path

from ..config import settings as default_settings
from ..core.session import Session
from ..providers import Provider
from ..schemas import Contract
from . import artifact as artifact_mod, camera, idle, screen

try:
    from plyer import notification
except ImportError:  # pragma: no cover
    notification = None  # type: ignore[assignment]


def notify(title: str, message: str) -> None:
    """Desktop notification if we can, terminal line regardless."""
    if notification is not None:
        try:
            notification.notify(title=title, message=message[:240], timeout=8)
            return
        except Exception:  # noqa: BLE001 - notifications are never worth a crash
            pass


def watch(
    provider: Provider,
    contract: Contract,
    *,
    once: bool = False,
    cadence_s: int | None = None,
    monitor: int = 1,
) -> int:
    settings = default_settings
    cadence = cadence_s or settings.cadence_s

    wants_screen = "screen" in contract.signals
    wants_camera = "camera" in contract.signals and camera.available()
    wants_diff = "diff" in contract.signals and bool(contract.artifacts)
    wants_idle = "idle" in contract.signals or wants_screen

    if wants_screen and not screen.available():
        print("screen signal requested but mss is not installed: pip install mss")
        return 1

    session = Session(provider, contract)
    watcher = artifact_mod.ArtifactWatcher(contract.artifacts, settle_s=settings.artifact_settle_s)
    tracker = idle.IdleTracker(threshold_s=cadence * 3)

    print(f"Heid Doon — session {session.id}")
    print(f"  task      {contract.task}")
    print(f"  signals   {', '.join(contract.signals)}")
    print(f"  model     {provider.model} via {provider.name}")
    print(f"  frames    judged in memory, never written to disk"
          f"{' — and never leave this machine' if provider.is_local else ' — SENT TO A HOSTED API'}")
    if wants_diff:
        missing = watcher.missing()
        print(f"  artifacts {', '.join(Path(p).name for p in contract.artifacts)}"
              f"{f'  (missing: {missing})' if missing else ''}")
        session.snapshot_artifacts()
    print(f"\nchecking every {cadence}s. Ctrl-C to stop and get your receipt.\n")

    last_hash: str | None = None
    last_on_task = True
    turn = 0

    try:
        while True:
            turn += 1
            turn_started = time.monotonic()
            checked_something = False

            if wants_screen:
                frame = screen.capture(monitor)
                current_hash = screen.frame_hash(frame)
                idle_s, unchanged = tracker.observe(current_hash)

                if current_hash == last_hash and last_on_task:
                    # Same screen as last time and it was fine then. Nothing to
                    # re-judge; spend the call budget on something that changed.
                    print(f"  {_clock()} ·  (screen unchanged)")
                else:
                    verdict = session.judge_frame(frame, kind="screen")
                    last_on_task = verdict.on_task
                    _report(verdict.on_task, verdict.seen, verdict.nudge, verdict.reason)
                    if not verdict.on_task and verdict.nudge:
                        notify("Heid Doon", verdict.nudge)
                    checked_something = True
                last_hash = current_hash
                del frame  # the frame's life ends here, explicitly

                if wants_idle:
                    event = session.note_idle(idle_s, unchanged)
                    if event:
                        print(f"  {_clock()} ○  {event.seen}")
                        notify("Heid Doon", str(event.detail.get("nudge", "")))

            # Camera on alternate turns: presence changes more slowly than screens,
            # and every frame costs a full inference.
            if wants_camera and turn % 2 == 0:
                try:
                    frame = camera.capture()
                except camera.CameraUnavailable as exc:
                    print(f"  {_clock()} ✗  camera: {exc}")
                else:
                    verdict = session.judge_frame(frame, kind="camera")
                    _report(verdict.on_task, verdict.seen, verdict.nudge, verdict.reason)
                    if not verdict.on_task and verdict.nudge:
                        notify("Heid Doon", verdict.nudge)
                    checked_something = True
                    del frame

            if wants_diff:
                for path in watcher.poll():
                    result = session.check_artifact(path)
                    if result is not None:
                        mark = {"progress": "▲", "padding": "≈", "stalled": "–"}.get(result.verdict, "·")
                        print(
                            f"  {_clock()} {mark}  {Path(path).name}: {result.verdict} "
                            f"({result.delta_words:+d} words) — {result.summary}"
                        )
                        if result.verdict == "padding":
                            notify("Heid Doon", result.quality_note or "That is words, not progress.")
                        checked_something = True

            if once:
                break

            # Sleep only the remainder of the cadence. If inference took longer
            # than the whole interval — which is the normal case on a CPU-only
            # laptop — say so once rather than pretending to a rhythm we are not
            # keeping, and carry straight on to the next check.
            spent = time.monotonic() - turn_started
            if spent > cadence and checked_something:
                if turn == 1 or turn % 10 == 0:
                    print(f"  {_clock()} !  a check-in took {spent:.0f}s, longer than the {cadence}s cadence")
                continue
            time.sleep(max(1.0, cadence - spent))

    except KeyboardInterrupt:
        print("\n\nwrapping up…")

    receipt = session.finish()
    print(f"\n── receipt ────────────────────────────────────────────────────")
    print(f"  focus score   {receipt.focus_score}/100")
    print(f"  autopsy       {receipt.autopsy}")
    print(f"  tomorrow      {receipt.tomorrow}")
    if receipt.learner_model.drift_patterns:
        print(f"  drift         {'; '.join(receipt.learner_model.drift_patterns)}")
    print(f"\n  session {session.id} saved to {session.store.path}")
    return 0


def _clock() -> str:
    return time.strftime("%H:%M:%S")


def _report(on_task: bool, seen: str, nudge: str, reason: str) -> None:
    mark = "●" if on_task else "○"
    line = f"  {_clock()} {mark}  {seen}"
    if on_task:
        print(line)
    else:
        print(f"{line}\n{' ' * 14}{nudge or reason}")
