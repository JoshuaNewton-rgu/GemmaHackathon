"""The interpretable decision layer.

Gemma perceives; these rules decide. The split is the point: a multimodal model is
irreplaceable at reading a messy screen into graded features, and terrible at being
audited. A fuzzy rule base is the opposite. Putting the model where perception
happens and readable arithmetic where policy happens means every intervention can be
traced to named rules, at known strengths, over degrees the student can check.
"""

from .engine import Decision, FiredRule, FuzzyEngine
from .library import DECISIONS, DEFAULT_RULES, PERCEPTS, default_rules, validate
from .rules import Clause, Rule, RuleSyntaxError, parse_rule
from .sets import FuzzySet, Variable, three_way

__all__ = [
    "Clause",
    "DECISIONS",
    "DEFAULT_RULES",
    "Decision",
    "FiredRule",
    "FuzzyEngine",
    "FuzzySet",
    "PERCEPTS",
    "Rule",
    "RuleSyntaxError",
    "Variable",
    "default_rules",
    "parse_rule",
    "three_way",
    "validate",
]


def engine() -> FuzzyEngine:
    """The configured engine, over the shipped percepts and decisions."""
    return FuzzyEngine(variables=PERCEPTS, outputs=DECISIONS)
