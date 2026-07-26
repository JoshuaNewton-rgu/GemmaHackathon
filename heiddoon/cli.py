"""Command line entry point.

    python -m heiddoon doctor          # is the model reachable, and how slow is it
    python -m heiddoon contract "..."  # compile a contract from your own words
    python -m heiddoon eval            # score the labelled frame set
    python -m heiddoon watch           # run a real session against your screen
    python -m heiddoon serve           # the web app
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import prompts
from .config import PROJECT_ROOT, Settings
from .core.contract import compile_contract, load_contract, save_contract
from .providers import DEFAULT_MODELS, Provider, ProviderError, get_provider

DEFAULT_CONTRACT_PATH = PROJECT_ROOT / "contract.json"
DEFAULT_TESTSET = PROJECT_ROOT / "testset"


# ── doctor ──────────────────────────────────────────────────────────────────


def cmd_doctor(args: argparse.Namespace) -> int:
    """Prove the model is reachable before anything else is debugged.

    Written because the failure this morning looked like three different bugs and
    was one: a model handle that was never verified against the backend serving it.
    """
    settings = Settings.from_env()
    print("── configuration ──────────────────────────────────────────────")
    print(f"  provider        {settings.provider}")
    print(f"  model           {settings.model or '(unset → ' + DEFAULT_MODELS.get(settings.provider, '?') + ')'}")
    print(f"  api key         {'set (' + str(len(settings.api_key)) + ' chars)' if settings.api_key else 'NOT SET'}")
    print(f"  ollama host     {settings.ollama_host}")
    print(f"  database        {settings.db_path}")
    print(f"  prompts         {prompts.PROMPT_VERSION}")

    try:
        provider = get_provider(settings)
    except ProviderError as exc:
        print(f"\n  ✗ cannot build provider: {exc}")
        return 1

    print(f"\n── reachable models ───────────────────────────────────────────")
    available: list[str] = []
    if hasattr(provider, "list_models"):
        try:
            available = provider.list_models()  # type: ignore[attr-defined]
        except ProviderError as exc:
            print(f"  ✗ {exc}")
        else:
            gemma = [name for name in available if "gemma" in name.lower()]
            for name in gemma or available[:15]:
                marker = "→" if name == provider.model else " "
                print(f"  {marker} {name}")
            if gemma and provider.model not in available:
                print(f"\n  ⚠ configured model {provider.model!r} is NOT in this list.")
                print(f"    Set HEIDDOON_MODEL to one of the handles above.")

    print(f"\n── text call ──────────────────────────────────────────────────")
    started = time.time()
    payload, meta = provider.complete_json('Reply with {"ok": true} and nothing else.', max_tokens=32)
    print(f"  {'✓' if meta.ok else '✗'} {round(time.time() - started, 1)}s  attempts={meta.attempts}  → {payload or meta.error}")
    if not meta.ok:
        print(f"    raw: {meta.raw[:200]}")
        return 1

    print(f"\n── vision call ────────────────────────────────────────────────")
    frame_path = Path(args.frame) if args.frame else next(iter(sorted(DEFAULT_TESTSET.glob("*.png"))), None)
    if frame_path is None or not frame_path.exists():
        print("  – skipped (no frame available)")
    else:
        from PIL import Image

        with Image.open(frame_path) as handle:
            frame = handle.convert("RGB")
        started = time.time()
        payload, meta = provider.complete_json(
            'What is in this image? Reply {"seen": "..."}', image=frame, max_tokens=120
        )
        elapsed = round(time.time() - started, 1)
        print(f"  {'✓' if meta.ok else '✗'} {elapsed}s  {frame_path.name}  → {str(payload or meta.error)[:160]}")
        if meta.ok:
            cadence = settings.cadence_s
            if elapsed > cadence:
                print(
                    f"\n  ⚠ one verdict takes {elapsed}s but the cadence is {cadence}s. The watcher will"
                    f"\n    fall behind. Either raise HEIDDOON_CADENCE_S above {int(elapsed) + 5}, or use a"
                    f"\n    faster backend for live watching."
                )

    print(f"\n── local signals ──────────────────────────────────────────────")
    for module, purpose in (("mss", "screen capture"), ("cv2", "webcam"), ("PIL", "frame encoding")):
        try:
            __import__(module)
        except ImportError:
            print(f"  ✗ {module:6} — {purpose} unavailable (pip install {'opencv-python' if module == 'cv2' else module})")
        else:
            print(f"  ✓ {module:6} — {purpose}")

    print(f"\n  frames leave this machine: {'NO — local inference' if provider.is_local else 'YES — hosted API'}")
    return 0


# ── contract ────────────────────────────────────────────────────────────────


def cmd_contract(args: argparse.Namespace) -> int:
    provider = get_provider()
    text = args.text or sys.stdin.read()
    contract, meta = compile_contract(provider, text)
    print(json.dumps(contract.to_dict(), indent=2, ensure_ascii=False))
    if contract._repairs:
        print(f"\nrepairs: {contract._repairs}", file=sys.stderr)
    if not meta.ok:
        print(f"\nmodel call failed: {meta.error}", file=sys.stderr)
        return 1
    if args.out:
        save_contract(contract, args.out)
        print(f"\nwritten: {args.out}", file=sys.stderr)
    return 0


# ── eval ────────────────────────────────────────────────────────────────────


def cmd_capture(args: argparse.Namespace) -> int:
    from .capture import capture_frame, print_status

    testset = Path(args.testset)
    if args.list or not args.name:
        print_status(testset)
        return 0
    return capture_frame(args.name, testset, delay=args.delay, camera=args.camera)


def cmd_eval(args: argparse.Namespace) -> int:
    from .evaluate import run_eval

    provider = get_provider()
    contract = load_contract(args.contract)
    report = run_eval(provider, args.testset, contract, out_path=args.out)
    headline = report["headline"]
    if not headline["n"]:
        return 2  # ran, but produced nothing quotable
    return 0


# ── watch ───────────────────────────────────────────────────────────────────


def cmd_watch(args: argparse.Namespace) -> int:
    from .watchers.loop import watch

    provider = get_provider()
    contract = load_contract(args.contract)
    return watch(provider, contract, once=args.once, cadence_s=args.cadence)


# ── serve ───────────────────────────────────────────────────────────────────


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print("the web app needs: pip install 'fastapi' 'uvicorn[standard]'", file=sys.stderr)
        return 1
    uvicorn.run("heiddoon.server:app", host=args.host, port=args.port, reload=args.reload)
    return 0


# ── wiring ──────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="heiddoon", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="check the provider, model handle and latency budget")
    doctor.add_argument("--frame", help="image to use for the vision check")
    doctor.set_defaults(func=cmd_doctor)

    contract = subparsers.add_parser("contract", help="compile a contract from natural language")
    contract.add_argument("text", nargs="?", help="the student's own words (or pipe on stdin)")
    contract.add_argument("--out", help="write the compiled contract here")
    contract.set_defaults(func=cmd_contract)

    capture = subparsers.add_parser("capture", help="capture a real frame for the eval test set")
    capture.add_argument("name", nargs="?", help="label name, or any unique part of it")
    capture.add_argument("--testset", default=str(DEFAULT_TESTSET))
    capture.add_argument("--delay", type=int, default=5, help="countdown seconds before the grab")
    capture.add_argument("--camera", action="store_true", help="force a webcam frame")
    capture.add_argument("--list", action="store_true", help="show what is captured and what is missing")
    capture.set_defaults(func=cmd_capture)

    evaluate = subparsers.add_parser("eval", help="score the labelled frame set")
    evaluate.add_argument("--testset", default=str(DEFAULT_TESTSET))
    evaluate.add_argument("--contract", default=str(DEFAULT_CONTRACT_PATH))
    evaluate.add_argument("--out", default="eval_results.json")
    evaluate.set_defaults(func=cmd_eval)

    watch = subparsers.add_parser("watch", help="run a live session against this machine")
    watch.add_argument("--contract", default=str(DEFAULT_CONTRACT_PATH))
    watch.add_argument("--once", action="store_true", help="one check-in, then exit")
    watch.add_argument("--cadence", type=int, default=None, help="seconds between check-ins")
    watch.set_defaults(func=cmd_watch)

    serve = subparsers.add_parser("serve", help="run the web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    return parser


def _force_utf8_output() -> None:
    """Stop a Windows console from killing the run over a tick mark.

    The default code page here is cp1252, which cannot encode the symbols the eval
    table prints, so the first '✗' raises UnicodeEncodeError and takes the whole
    command down — losing a completed eval on the way out.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except ProviderError as exc:
        print(f"provider error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nstopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
