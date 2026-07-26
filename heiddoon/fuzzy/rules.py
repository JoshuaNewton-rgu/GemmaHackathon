"""Rules, written and stored as the sentences a student can read.

A rule's canonical form here is its text:

    IF topic_match is low AND drift is long THEN nudge is firm

It is parsed from that, rendered back to it, and edited as it. That is deliberate:
if the readable form were generated *from* a structure, the two could drift apart and
the sentence shown to the student would stop being the rule that fired. Here there is
only one artefact, so the explanation cannot lie.

Every rule also carries a `because` — why it exists at all. When the expert agent
proposes a weight change, that is where its reasoning goes, so the rule base
accumulates its own history rather than silently mutating.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

Connective = Literal["and", "or"]

_RULE = re.compile(
    r"^\s*IF\s+(?P<when>.+?)\s+THEN\s+(?P<var>\w+)\s+is\s+(?P<set>[\w-]+)\s*$",
    re.IGNORECASE,
)
_CLAUSE = re.compile(r"^\s*(?P<var>\w+)\s+is\s+(?P<neg>not\s+)?(?P<set>[\w-]+)\s*$", re.IGNORECASE)


class RuleSyntaxError(ValueError):
    """The rule text could not be read. Reported with the offending text."""


@dataclass(frozen=True)
class Clause:
    variable: str
    set_name: str
    negated: bool = False

    def text(self) -> str:
        return f"{self.variable} is {'not ' if self.negated else ''}{self.set_name}"

    def degree(self, memberships: dict[str, dict[str, float]]) -> float:
        """How true this clause is, given every variable's memberships."""
        value = memberships.get(self.variable, {}).get(self.set_name, 0.0)
        return 1.0 - value if self.negated else value


@dataclass
class Rule:
    id: str
    when: tuple[Clause, ...]
    then_variable: str
    then_set: str
    weight: float = 1.0
    connective: Connective = "and"
    because: str = ""
    #: Set when a rule's weight has been changed from the shipped default, so the UI
    #: can show what has been tuned for this student and what is still stock.
    tuned: bool = False
    history: list[str] = field(default_factory=list)

    def text(self) -> str:
        joiner = f" {self.connective.upper()} "
        return (
            f"IF {joiner.join(clause.text() for clause in self.when)} "
            f"THEN {self.then_variable} is {self.then_set}"
        )

    def strength(self, memberships: dict[str, dict[str, float]]) -> tuple[float, list[float]]:
        """Firing strength, and each clause's degree for the explanation.

        AND takes the minimum and OR the maximum — Zadeh's operators. Chosen over
        the probabilistic alternatives because min/max are what a reader intuits from
        the words: an AND rule is exactly as true as its weakest part.
        """
        degrees = [clause.degree(memberships) for clause in self.when]
        if not degrees:
            return 0.0, []
        combined = min(degrees) if self.connective == "and" else max(degrees)
        return combined * self.weight, degrees

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text(),
            "weight": round(self.weight, 3),
            "because": self.because,
            "tuned": self.tuned,
            "history": self.history,
            "then_variable": self.then_variable,
            "then_set": self.then_set,
        }


def parse_rule(text: str, *, rule_id: str = "", weight: float = 1.0, because: str = "") -> Rule:
    """Read one rule from its sentence.

    Raises RuleSyntaxError with the offending text rather than a generic parse error:
    these are edited by hand and by an agent, and both need to be told which sentence
    was wrong.
    """
    match = _RULE.match(text)
    if not match:
        raise RuleSyntaxError(f"expected 'IF <clauses> THEN <var> is <set>', got: {text!r}")

    when_text = match.group("when")
    connective: Connective = "or" if re.search(r"\bOR\b", when_text, re.IGNORECASE) else "and"
    parts = re.split(r"\bAND\b|\bOR\b", when_text, flags=re.IGNORECASE)

    clauses: list[Clause] = []
    for part in parts:
        clause_match = _CLAUSE.match(part)
        if not clause_match:
            raise RuleSyntaxError(f"could not read condition {part.strip()!r} in: {text!r}")
        clauses.append(
            Clause(
                variable=clause_match.group("var").lower(),
                set_name=clause_match.group("set").lower(),
                negated=bool(clause_match.group("neg")),
            )
        )

    return Rule(
        id=rule_id or _slug(text),
        when=tuple(clauses),
        then_variable=match.group("var").lower(),
        then_set=match.group("set").lower(),
        weight=weight,
        connective=connective,
        because=because,
    )


def _slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words[:6])
