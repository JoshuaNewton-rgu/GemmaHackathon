"""Mamdani inference with a complete audit trail.

The trail is not a by-product here, it is the deliverable. A binary verdict from a
model can only ever be explained after the fact, by asking the model to justify
itself — which produces plausible prose with no causal link to the decision. This
engine instead *is* the decision: the numbers below are what determined the outcome,
so the explanation is a reading of the arithmetic rather than a story about it.

Aggregation is max over each output set's firing strengths, and defuzzification is a
weighted average of set centroids. Centroid-of-set rather than centroid-of-area
because it keeps every output traceable to whole rules — the number can always be
decomposed back into "these rules, at these strengths".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .rules import Rule
from .sets import Variable


@dataclass
class FiredRule:
    """One rule that contributed, and the arithmetic that made it contribute."""

    rule: Rule
    strength: float
    clause_degrees: list[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.rule.id,
            "text": self.rule.text(),
            "strength": round(self.strength, 3),
            "weight": round(self.rule.weight, 3),
            "because": self.rule.because,
            "clauses": [
                {"text": clause.text(), "degree": round(degree, 3)}
                for clause, degree in zip(self.rule.when, self.clause_degrees)
            ],
            "concludes": f"{self.rule.then_variable} is {self.rule.then_set}",
        }


@dataclass
class Decision:
    """What the engine concluded, and everything needed to check it."""

    inputs: dict[str, float]
    memberships: dict[str, dict[str, float]]
    fired: list[FiredRule]
    outputs: dict[str, float]
    output_words: dict[str, str]
    #: How strongly each output was asked for at all — the firing strength of the
    #: best rule that concluded it. Separate from `outputs` because defuzzification
    #: deliberately throws this away: a weighted average of centroids divides the
    #: activation out, so a rule that is 3% true and one that is 75% true produce
    #: the same value when they are the only rule concluding their variable. That is
    #: correct for "where between silent and firm does this sit", and useless for
    #: "is there enough here to interrupt someone" — which is what callers need.
    activation: dict[str, float] = field(default_factory=dict)
    #: Rules that matched nothing. Kept because "no rule covers this situation" is a
    #: finding about the rule base, not an absence of information.
    silent: list[str] = field(default_factory=list)

    def top_rules(self, limit: int = 3) -> list[FiredRule]:
        return sorted(self.fired, key=lambda item: -item.strength)[:limit]

    def why(self, output_variable: str | None = None) -> str:
        """The explanation, read off the arithmetic.

        Deliberately assembled from the trace rather than written by a model: this
        sentence is true by construction, because it names the rules that actually
        determined the output and the degrees that made them fire.
        """
        relevant = [
            item
            for item in self.fired
            if output_variable is None or item.rule.then_variable == output_variable
        ]
        if not relevant:
            # Read by a student, not a debugger: an empty rule set is not an error or a
            # shrug, it is the default outcome. Nothing fired, so nothing happened.
            return "No rule asked for anything here, so nothing happened — silence is the default."

        relevant.sort(key=lambda item: -item.strength)
        lead = relevant[0]
        reasons = " and ".join(
            f"{clause['text']} ({clause['degree']:.0%})"
            for clause in lead.to_dict()["clauses"]
        )
        sentence = f"{lead.rule.then_variable} is {lead.rule.then_set} because {reasons}"
        if len(relevant) > 1:
            sentence += f", and {len(relevant) - 1} weaker rule(s) agreed or pulled against it"
        return sentence

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputs": {name: round(value, 3) for name, value in self.inputs.items()},
            "memberships": {
                name: {word: round(degree, 3) for word, degree in words.items() if degree > 0}
                for name, words in self.memberships.items()
            },
            "fired": [item.to_dict() for item in self.top_rules(limit=12)],
            "outputs": {name: round(value, 3) for name, value in self.outputs.items()},
            "output_words": self.output_words,
            "activation": {name: round(value, 3) for name, value in self.activation.items()},
            "silent": self.silent,
            "why": self.why(),
        }


class FuzzyEngine:
    def __init__(self, variables: dict[str, Variable], outputs: dict[str, Variable]) -> None:
        self.variables = variables
        self.outputs = outputs

    def infer(self, rules: list[Rule], inputs: dict[str, float]) -> Decision:
        known = {**self.variables, **self.outputs}

        # Membership for every input we were given and know about. An input with no
        # declared variable is ignored rather than guessed at — a typo in a feature
        # name must not silently become a rule that never fires.
        memberships: dict[str, dict[str, float]] = {}
        for name, value in inputs.items():
            variable = known.get(name)
            if variable is not None:
                memberships[name] = variable.memberships(value)

        fired: list[FiredRule] = []
        silent: list[str] = []
        for rule in rules:
            strength, degrees = rule.strength(memberships)
            if strength > 0.0:
                fired.append(FiredRule(rule=rule, strength=strength, clause_degrees=degrees))
            else:
                silent.append(rule.id)

        # Aggregate: each output set takes the strongest rule that concluded it.
        per_set: dict[str, dict[str, float]] = {}
        for item in fired:
            bucket = per_set.setdefault(item.rule.then_variable, {})
            bucket[item.rule.then_set] = max(bucket.get(item.rule.then_set, 0.0), item.strength)

        crisp: dict[str, float] = {}
        words: dict[str, str] = {}
        activation: dict[str, float] = {}
        for variable_name, activations in per_set.items():
            output = self.outputs.get(variable_name)
            if output is None:
                continue
            activation[variable_name] = max(activations.values())
            numerator = 0.0
            denominator = 0.0
            for set_name, set_activation in activations.items():
                fuzzy_set = output.set_named(set_name)
                if fuzzy_set is None:
                    continue
                numerator += fuzzy_set.centroid * set_activation
                denominator += set_activation
            if denominator > 0:
                crisp[variable_name] = numerator / denominator
                words[variable_name] = max(activations, key=lambda name: activations[name])

        return Decision(
            inputs=dict(inputs),
            memberships=memberships,
            fired=fired,
            outputs=crisp,
            output_words=words,
            activation=activation,
            silent=silent,
        )
