"""The eval — the one number that decides whether any of the rest is true.

Three rules are enforced in code, because each one is a way a demo number quietly
becomes a lie:

1. **Mock output can never be reported.** If the configured provider is the mock,
   the harness refuses to write a result file at all.
2. **Synthetic frames are scored separately from real ones.** Rendered mock-ups of a
   video site are read by the model as text and pass trivially; they measure nothing
   about screen understanding. The headline number is over real captures only.
3. **Frames that did not run are counted.** A missing file is reported as not-run
   rather than silently dropped from the denominator, so "6/6" cannot hide the fact
   that five of eleven cases never executed.

The breakdown separates false accusations from missed drift, because they are not
equally bad: a wrong nudge teaches the student to distrust the app, and a distrusted
app gets uninstalled.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from . import prompts
from .core.verdict import judge_frame
from .providers import Provider
from .schemas import Contract


@dataclass
class FrameResult:
    file: str
    case: str
    kind: str
    source: str
    expected: bool
    got: bool | None
    correct: bool
    seen: str = ""
    reason: str = ""
    confidence: str = ""
    latency_s: float = 0.0
    repairs: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "case": self.case,
            "kind": self.kind,
            "source": self.source,
            "expected_on_task": self.expected,
            "got_on_task": self.got,
            "correct": self.correct,
            "seen": self.seen,
            "reason": self.reason,
            "confidence": self.confidence,
            "latency_s": round(self.latency_s, 2),
            "repairs": self.repairs,
            "error": self.error,
        }


def _score(results: list[FrameResult]) -> dict[str, Any]:
    if not results:
        return {"accuracy": None, "n": 0}
    correct = sum(1 for result in results if result.correct)
    # A false accusation: we said drift, the label says they were working.
    false_accusations = [r for r in results if r.expected and r.got is False]
    missed_drift = [r for r in results if not r.expected and r.got is True]
    return {
        "accuracy": f"{correct}/{len(results)}",
        "accuracy_pct": round(100 * correct / len(results), 1),
        "n": len(results),
        "false_accusations": len(false_accusations),
        "false_accusation_files": [r.file for r in false_accusations],
        "missed_drift": len(missed_drift),
        "missed_drift_files": [r.file for r in missed_drift],
    }


def run_eval(
    provider: Provider,
    test_dir: str | Path,
    contract: Contract,
    *,
    out_path: str | Path | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Score the labelled frame set and return the report."""
    test_dir = Path(test_dir)
    labels: dict[str, dict[str, Any]] = json.loads((test_dir / "labels.json").read_text(encoding="utf-8"))

    results: list[FrameResult] = []
    not_run: list[dict[str, str]] = []
    started = time.time()

    for filename, meta in labels.items():
        if filename.startswith("_"):
            continue  # `_readme` and friends: documentation, not a frame
        path = test_dir / filename
        if not path.exists():
            not_run.append(
                {"file": filename, "why": str(meta.get("note", "file missing")), "source": str(meta.get("source", "?"))}
            )
            if verbose:
                print(f"  – NOT RUN  {filename}  — {meta.get('note', 'no such file')}")
            continue

        source = str(meta.get("source", "unspecified"))
        expected = bool(meta["on_task"])
        kind = str(meta.get("kind", "screen"))

        try:
            with Image.open(path) as handle:
                frame = handle.convert("RGB")
            verdict, call = judge_frame(provider, contract, frame, expect_kind=kind)
        except Exception as exc:  # noqa: BLE001 - one bad frame must not end the run
            results.append(
                FrameResult(
                    file=filename, case=str(meta.get("case", "?")), kind=kind, source=source,
                    expected=expected, got=None, correct=False, error=f"{type(exc).__name__}: {exc}",
                )
            )
            if verbose:
                print(f"  ✗ ERROR    {filename}  {type(exc).__name__}: {exc}")
            continue

        correct = verdict.on_task == expected
        results.append(
            FrameResult(
                file=filename,
                case=str(meta.get("case", "?")),
                kind=kind,
                source=source,
                expected=expected,
                got=verdict.on_task,
                correct=correct,
                seen=verdict.seen,
                reason=verdict.reason,
                confidence=verdict.confidence,
                latency_s=call.latency_s,
                repairs=list(verdict._repairs),
            )
        )
        if verbose:
            mark = "✓" if correct else "✗"
            print(f"  {mark} [{meta.get('case','?'):4}|{source:9}] {filename:28} → {verdict.seen[:60]}")
            if not correct:
                print(f"      expected on_task={expected}, got {verdict.on_task} — {verdict.reason[:90]}")

    real = [result for result in results if result.source == "real"]
    synthetic = [result for result in results if result.source == "synthetic"]
    latencies = [result.latency_s for result in results if result.latency_s > 0]
    repaired = sum(1 for result in results if result.repairs)

    report = {
        "headline": _score(real),
        "synthetic_only": _score(synthetic),
        "all_frames_mixed": _score(results),
        "hard_cases_real": _score([result for result in real if result.case == "hard"]),
        "by_kind_real": {
            kind: _score([result for result in real if result.kind == kind]) for kind in ("screen", "camera")
        },
        "not_run": not_run,
        "coverage": {
            "labelled": sum(1 for name in labels if not name.startswith("_")),
            "executed": len(results),
            "real": len(real),
            "synthetic": len(synthetic),
        },
        "reliability": {
            "json_repairs": repaired,
            "clean_rate_pct": round(100 * (len(results) - repaired) / len(results), 1) if results else None,
        },
        "latency_s": {
            "median": round(statistics.median(latencies), 2) if latencies else None,
            "max": round(max(latencies), 2) if latencies else None,
        },
        "run": {
            "provider": provider.name,
            "model": provider.model,
            "local_inference": provider.is_local,
            "prompt_version": prompts.PROMPT_VERSION,
            "test_dir": str(test_dir),
            "wall_clock_s": round(time.time() - started, 1),
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "results": [result.to_dict() for result in results],
    }

    if verbose:
        print_summary(report)

    if out_path:
        if provider.name == "mock":
            print(
                "\nREFUSING to write eval results: the provider is the mock. "
                "Mock output must never end up in a file that looks like a measurement."
            )
        else:
            Path(out_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            if verbose:
                print(f"\nwritten: {out_path}")

    return report


def print_summary(report: dict[str, Any]) -> None:
    run = report["run"]
    coverage = report["coverage"]
    headline = report["headline"]
    synthetic = report["synthetic_only"]

    print("\n" + "═" * 74)
    print(f"  HEID DOON EVAL · {run['model']} via {run['provider']} · prompts {run['prompt_version']}")
    print("═" * 74)

    if headline["n"]:
        print(f"  QUOTABLE NUMBER (real captures)   {headline['accuracy']}  ({headline['accuracy_pct']}%)")
        hard = report["hard_cases_real"]
        if hard["n"]:
            print(f"    of which hard cases             {hard['accuracy']}")
        print(f"    false accusations               {headline['false_accusations']}  {headline['false_accusation_files'] or ''}")
        print(f"    missed drift                    {headline['missed_drift']}  {headline['missed_drift_files'] or ''}")
    else:
        print("  QUOTABLE NUMBER                   none — no real captures in the test set")
        print("    Every executed frame is a synthetic mock-up. A rendered mock-up of a")
        print("    video page is read as text, so it measures nothing about real screen")
        print("    understanding. Capture real frames before quoting any number.")

    if synthetic["n"]:
        print(f"\n  synthetic frames (NOT quotable)    {synthetic['accuracy']}  ({synthetic['accuracy_pct']}%)")

    print(
        f"\n  coverage   {coverage['executed']}/{coverage['labelled']} labelled frames executed"
        f"  ·  {coverage['real']} real, {coverage['synthetic']} synthetic"
    )
    for entry in report["not_run"]:
        print(f"    not run: {entry['file']} — {entry['why']}")

    reliability = report["reliability"]
    latency = report["latency_s"]
    print(
        f"  json       {reliability['json_repairs']} responses needed repair"
        f"  ·  {reliability['clean_rate_pct']}% clean"
    )
    if latency["median"] is None:
        print("  latency    not measured")
    else:
        print(f"  latency    median {latency['median']}s  ·  worst {latency['max']}s")

    if run["provider"] == "mock":
        where = "nowhere — the mock provider ran no model"
    elif run["local_inference"]:
        where = "LOCAL — frames stayed on this machine"
    else:
        where = "HOSTED API — frames left this machine"
    print(f"  inference  {where}")
    print("═" * 74)
