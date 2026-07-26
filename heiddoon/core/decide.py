"""Perception in, decision out, with the reasoning attached.

The order here is the whole architecture: perceive, measure, infer, and only then —
if and only if the rules asked for it — write a sentence. The model never decides
whether to interrupt. It reads the screen at the start and, at the end, phrases a
decision that has already been made and can be shown as arithmetic.

That also means an unreachable model cannot produce an intervention. Perception fails
to zero confidence, the rule base turns low confidence into silence, and the student
is left alone. The failure mode is quiet, not accusatory.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .. import prompts
from ..fuzzy import Decision, Rule, engine as build_engine
from ..providers import Provider
from ..schemas import Contract, Event
from . import perceive as perceive_mod
from .perceive import Perception
from .verdict import _fallback_nudge

#: How true a rule has to be before it is allowed to interrupt someone.
#:
#: These gate the *firing strength* — how strongly the rules asked — and not the
#: defuzzified value, which cannot answer the question. Defuzzification is a weighted
#: average of set centroids, so it divides the activation back out: when one set is
#: active the result is that set's centroid whatever strength produced it. Gating on it
#: meant a rule that was 3% true interrupted exactly as readily as one that was 75%
#: true, which is the false-accusation path this product is organised against.
ACT_STRENGTH = 0.40
#: Higher, because asking to see the page costs the student something every time. The
#: intrusion policy is that an interruption must be earned by evidence, so the bar for
#: spending one is above the bar for speaking.
ASK_STRENGTH = 0.45
#: Lower: mentioning a break is the least intrusive thing here, and a break offered
#: early is a break that never has to be stolen.
BREAK_STRENGTH = 0.35


@dataclass
class Outcome:
    """A decision, its reasoning, and the words that came out of it."""

    perception: Perception
    decision: Decision
    nudge_line: str = ""
    act: bool = False
    firmness: str = "silent"
    break_offer: str = "none"
    ask_page: str = "no"
    latency_s: float = 0.0
    repairs: list[str] = field(default_factory=list)

    @property
    def on_task(self) -> bool:
        """A binary read, for anything that still needs one — the eval especially.

        Derived from the percept rather than from the decision: whether someone is on
        task is a fact about the frame, while whether to speak about it is a policy
        question, and collapsing the two is what the fuzzy layer exists to undo.
        """
        return self.perception.topic_match >= 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "perception": self.perception.to_dict(),
            "on_task": self.on_task,
            "act": self.act,
            "firmness": self.firmness,
            "nudge": self.nudge_line,
            "break_offer": self.break_offer,
            "ask_page": self.ask_page,
            "trace": self.decision.to_dict(),
            "latency_s": round(self.latency_s, 2),
        }


def decide(
    provider: Provider,
    contract: Contract,
    image: Any,
    *,
    rules: list[Rule],
    events: list[Event],
    started_at: float,
    last_break_at: float | None = None,
    kind: str = "screen",
    write_line: bool = True,
) -> Outcome:
    """The full path: perceive, measure, infer, and speak only if told to."""
    began = time.time()
    perception, meta = perceive_mod.perceive(provider, contract, image, kind=kind)

    inputs = {
        # perceived
        "topic_match": perception.topic_match,
        "is_own_work": perception.is_own_work,
        "padding": perception.padding,
        "confidence": perception.confidence,
        # measured
        "drift": perceive_mod.measure_drift(events),
        "fatigue": perceive_mod.measure_fatigue(started_at, last_break_at),
        "progress": perceive_mod.measure_progress(events),
        "presence": perceive_mod.measure_presence(events),
    }

    decision = build_engine().infer(rules, inputs)
    firmness = decision.output_words.get("nudge", "silent")
    act = firmness != "silent" and decision.activation.get("nudge", 0.0) >= ACT_STRENGTH

    outcome = Outcome(
        perception=perception,
        decision=decision,
        act=act,
        # Firmness is reported as what the rules concluded even when it was too weak to
        # act on, because the trace has to show what nearly happened. `act` is the only
        # thing that decides whether the student hears about it.
        firmness=firmness,
        break_offer=_gated(decision, "break_offer", BREAK_STRENGTH, "none"),
        ask_page=_gated(decision, "ask_page", ASK_STRENGTH, "no"),
        repairs=list(meta.repairs),
    )

    if act:
        # Not writing the line is a choice about who phrases it, never a choice to
        # interrupt someone with nothing to read. The model-free line quotes their own
        # stated reason back at them, which is what the prompt is asked to do anyway.
        outcome.nudge_line = (
            write_nudge(provider, contract, perception.seen, firmness)
            if write_line
            else _fallback_nudge(contract)
        )

    outcome.latency_s = time.time() - began
    return outcome


def _gated(decision: Decision, variable: str, floor: float, quiet: str) -> str:
    """The rules' conclusion, or `quiet` when they did not ask hard enough.

    Without this a single weak rule wins its variable by default — it is the only one
    concluding anything about it, so aggregation has nothing to weigh it against. That
    is how a rule firing at 0.16 came to ask a student who was demonstrably on task to
    photograph their page.
    """
    if decision.activation.get(variable, 0.0) < floor:
        return quiet
    return decision.output_words.get(variable, quiet)


def write_nudge(provider: Provider, contract: Contract, seen: str, firmness: str) -> str:
    """Phrase the interruption the rules already decided on.

    A separate, tiny call rather than a field on the perception call: asking for a
    nudge up front means one gets written on every frame including the ones that end
    in silence, which is both wasteful and a standing temptation to use it.
    """
    raw, meta = provider.complete_json(
        prompts.render(
            prompts.NUDGE_LINE,
            contract=contract.for_prompt(),
            seen=seen or "something off task",
            firmness=firmness,
        ),
        max_tokens=250,
    )
    line = str(raw.get("line", "")).strip() if meta.ok else ""
    line = line.replace("!", ".").strip()
    if not line:
        # The fallback quotes the student's own reason, which is the same thing the
        # prompt is asked to do — so a failed call degrades in tone, not in kind.
        from .verdict import _fallback_nudge

        return _fallback_nudge(contract)
    return line
