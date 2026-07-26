"""F1 — the contract compiler: the student's own words become the rules.

This is the autonomy mechanic. Everything downstream is judged against whatever
comes out of here, which is why the compiler is instructed never to add a
restriction the student did not ask for.
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import prompts
from ..providers import CallMeta, Provider
from ..schemas import Contract

VALID_SIGNALS = ("screen", "camera", "diff", "idle")


def compile_contract(provider: Provider, text: str) -> tuple[Contract, CallMeta]:
    """Natural language in, structured rules out."""
    raw, meta = provider.complete_json(
        prompts.render(prompts.CONTRACT_COMPILER, text=text.strip()),
        max_tokens=700,
    )
    contract = Contract.from_model(raw)

    # Drop signals we have no watcher for, rather than carrying a name that will
    # silently never fire.
    unknown = [signal for signal in contract.signals if signal not in VALID_SIGNALS]
    if unknown:
        contract.signals = [signal for signal in contract.signals if signal in VALID_SIGNALS]
        contract._repairs.append(f"signals: dropped unsupported {unknown}")
    if not contract.signals:
        contract.signals = ["screen"]
        contract._repairs.append("signals: empty, defaulted to ['screen']")

    # A contract with no task cannot be judged against; fail loudly here rather
    # than producing confidently wrong verdicts for the rest of the session.
    if not contract.task:
        contract._repairs.append("task: empty — contract is unusable")

    contract._meta = meta.to_dict()
    meta.repairs = list(contract._repairs)
    return contract, meta


def load_contract(path: str | Path) -> Contract:
    """Read a contract from disk — how the local watcher picks up its rules."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Contract.from_model(data)


def save_contract(contract: Contract, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(contract.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
