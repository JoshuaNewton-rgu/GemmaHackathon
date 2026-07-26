"""Linguistic variables and their fuzzy sets.

The point of the whole fuzzy layer is that a student can read why they were
interrupted. That only works if the vocabulary is the vocabulary they would use:
`topic_match is low`, `drift is long`, `progress is high`. So the variables are
named for what they mean, each carries its own description, and the sets are the
words — never thresholds.

A trapezoid covers every shape needed here: give it four points and a triangle is
just the case where the middle two coincide, a left shoulder is where the first two
do, a right shoulder the last two. One function, no special cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FuzzySet:
    """One word — "low", "long", "high" — as a trapezoidal membership function.

    Points (a, b, c, d) rise from 0 at a to 1 at b, hold, and fall to 0 at d.
    """

    name: str
    a: float
    b: float
    c: float
    d: float

    def mu(self, x: float) -> float:
        """Degree to which `x` belongs to this set, in [0, 1]."""
        if x <= self.a or x >= self.d:
            # A shoulder set has a == b (or c == d), so an input sitting exactly on
            # the flat top must not be excluded by the boundary test above.
            if self.a == self.b and x <= self.a:
                return 1.0 if x >= self.a else 0.0
            if self.c == self.d and x >= self.d:
                return 1.0 if x <= self.d else 0.0
            return 0.0
        if x < self.b:
            return (x - self.a) / (self.b - self.a)
        if x <= self.c:
            return 1.0
        return (self.d - x) / (self.d - self.c)

    @property
    def centroid(self) -> float:
        """Representative value, used when defuzzifying by weighted average."""
        return (self.a + self.b + self.c + self.d) / 4.0


def triangle(name: str, a: float, peak: float, c: float) -> FuzzySet:
    return FuzzySet(name, a, peak, peak, c)


def left_shoulder(name: str, top_to: float, zero_at: float) -> FuzzySet:
    """Fully a member at 0, fading out by `zero_at`."""
    return FuzzySet(name, 0.0, 0.0, top_to, zero_at)


def right_shoulder(name: str, rise_from: float, top_from: float) -> FuzzySet:
    """Fading in from `rise_from`, fully a member by `top_from` and beyond."""
    return FuzzySet(name, rise_from, top_from, 1.0, 1.0)


@dataclass(frozen=True)
class Variable:
    """A named quantity in [0, 1], carved into overlapping words."""

    name: str
    description: str
    sets: tuple[FuzzySet, ...]
    #: What the raw number means at 0 and at 1, so the UI can label an axis without
    #: the reader having to infer the direction.
    low_label: str = ""
    high_label: str = ""

    def memberships(self, x: float) -> dict[str, float]:
        value = max(0.0, min(1.0, float(x)))
        return {fuzzy_set.name: fuzzy_set.mu(value) for fuzzy_set in self.sets}

    def set_named(self, name: str) -> FuzzySet | None:
        for fuzzy_set in self.sets:
            if fuzzy_set.name == name:
                return fuzzy_set
        return None

    def strongest(self, x: float) -> str:
        """The single word that best describes `x` — for one-line summaries."""
        memberships = self.memberships(x)
        return max(memberships, key=lambda name: memberships[name])


def three_way(
    name: str,
    description: str,
    words: tuple[str, str, str] = ("low", "medium", "high"),
    *,
    low_label: str = "",
    high_label: str = "",
) -> Variable:
    """The standard low / medium / high carve-up, with deliberate overlap.

    Two properties this partition is built to hold, both tested:

    - **Full coverage.** Every value in [0, 1] belongs to at least one word, so no
      input can arrive that the rules are silent about for lack of vocabulary.
    - **Overlap at the crossovers.** Around 0.35 a value is partly low and partly
      medium, which is the nuance a crisp threshold destroys. The midpoint 0.5 is
      deliberately *pure* medium — that is what makes "medium" mean something.
    """
    low, medium, high = words
    return Variable(
        name=name,
        description=description,
        sets=(
            left_shoulder(low, 0.15, 0.45),
            triangle(medium, 0.25, 0.5, 0.75),
            right_shoulder(high, 0.55, 0.85),
        ),
        low_label=low_label,
        high_label=high_label,
    )
