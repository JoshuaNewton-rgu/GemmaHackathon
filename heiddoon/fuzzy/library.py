"""The domain model: what Heid Doon perceives, and the rules it reasons with.

This file is the product's policy, written where a student can read it. Everything
the app does to someone — nudge, stay quiet, suggest a break, ask for a page — comes
out of these sentences, and any of them can be reweighted or removed.

The design principles from the design doc stop being aspirations here and become
arithmetic:

- **Compassion** — no rule concludes a firm nudge from a single drift reading, and
  `protect-flow` outranks every interruption rule when the work is moving.
- **Truth** — progress rules read the artifact, never the activity.
- **Autonomy** — the student's contract supplies `topic_match`; these rules only say
  what to do about degrees, never what counts as on-topic.
"""

from __future__ import annotations

from .rules import Rule, parse_rule
from .sets import Variable, three_way

# ── what the model is asked to perceive ─────────────────────────────────────
# Every one of these is a degree in [0, 1] read off a frame or the event log, and
# each has to be something a person could also judge by looking — otherwise the
# explanation names a quantity the student cannot check.

PERCEPTS: dict[str, Variable] = {
    "topic_match": three_way(
        "topic_match",
        "How closely what is on screen relates to the contracted task",
        low_label="unrelated",
        high_label="exactly the task",
    ),
    "is_own_work": three_way(
        "is_own_work",
        "Whether this is the student's own writing rather than something they are reading",
        low_label="consuming",
        high_label="writing",
    ),
    "drift": three_way(
        "drift",
        "How long the student has been away from the task",
        words=("brief", "moderate", "long"),
        low_label="just now",
        high_label="a long stretch",
    ),
    "progress": three_way(
        "progress",
        "How much genuinely new material has appeared in the work",
        words=("stalled", "some", "strong"),
        low_label="nothing new",
        high_label="moving well",
    ),
    "padding": three_way(
        "padding",
        "How much of the new writing is filler rather than substance",
        low_label="substantive",
        high_label="filler",
    ),
    "fatigue": three_way(
        "fatigue",
        "How long the student has worked without a break",
        low_label="fresh",
        high_label="overdue a break",
    ),
    "presence": three_way(
        "presence",
        "Whether the student is at the desk and engaged",
        words=("absent", "partial", "present"),
        low_label="not there",
        high_label="at the desk",
    ),
    "confidence": three_way(
        "confidence",
        "How sure the perception layer is about what it saw",
        low_label="a guess",
        high_label="unambiguous",
    ),
}

# ── what the engine decides ─────────────────────────────────────────────────

DECISIONS: dict[str, Variable] = {
    "nudge": three_way(
        "nudge",
        "How firmly to interrupt, if at all",
        words=("silent", "gentle", "firm"),
        low_label="say nothing",
        high_label="interrupt clearly",
    ),
    "break_offer": three_way(
        "break_offer",
        "How strongly to offer a break",
        words=("none", "mention", "urge"),
        low_label="do not raise it",
        high_label="push for one",
    ),
    "ask_page": three_way(
        "ask_page",
        "Whether to ask to see the student's page",
        words=("no", "maybe", "yes"),
        low_label="do not ask",
        high_label="ask now",
    ),
}


#: (text, weight, because). Order is presentation order; it does not affect inference.
DEFAULT_RULES: list[tuple[str, float, str]] = [
    # ── staying quiet is a decision too ─────────────────────────────────────
    (
        "IF progress is strong THEN nudge is silent",
        1.0,
        "Work that is moving must never be interrupted. This is the highest-weighted "
        "silence rule because breaking concentration to praise it is the single most "
        "damaging thing a focus tool can do.",
    ),
    (
        "IF topic_match is high AND is_own_work is high THEN nudge is silent",
        0.95,
        "Writing about the contracted topic is the target state. Nothing to say.",
    ),
    (
        "IF confidence is low THEN nudge is silent",
        0.9,
        "An uncertain reading must not become an accusation. A wrong nudge costs more "
        "trust than a missed drift, so low confidence buys silence rather than a guess. "
        "Note that this rule is a backstop, not the mechanism: every rule that acts "
        "carries 'AND confidence is not low' in its own conditions, so an unclear frame "
        "stops those rules firing at all rather than merely arguing with them. Written "
        "as a competing preference it lost to a strong drift rule — which the trace "
        "showed plainly, and is the sort of thing this architecture exists to expose.",
    ),
    # ── drift, proportionate to how long it has gone on ─────────────────────
    (
        "IF topic_match is low AND drift is brief AND confidence is not low THEN nudge is gentle",
        0.8,
        "A moment off task is not a lapse. The first word is quiet and warm.",
    ),
    (
        "IF topic_match is low AND drift is moderate AND confidence is not low THEN nudge is gentle",
        0.9,
        "Still gentle, but more likely to be the loudest rule firing.",
    ),
    (
        "IF topic_match is low AND drift is long AND confidence is not low THEN nudge is firm",
        1.0,
        "A long stretch away has earned a clear word. Firm is not unkind: it is the "
        "only honest response once a gentle nudge has demonstrably not worked.",
    ),
    (
        "IF presence is absent AND drift is long AND confidence is not low THEN nudge is firm",
        0.85,
        "Nobody at the desk and the work untouched. The camera and the idle signal "
        "agree, which is the one case worth being direct about.",
    ),
    # ── the work itself ─────────────────────────────────────────────────────
    (
        "IF padding is high AND topic_match is high AND confidence is not low THEN nudge is gentle",
        0.7,
        "Writing filler about the right subject is still avoidance, and it is the "
        "kindest possible thing to point out early — the student usually knows.",
    ),
    (
        "IF progress is stalled AND is_own_work is high AND drift is brief THEN nudge is silent",
        0.75,
        "Staring at your own work having written nothing is thinking, not drifting. "
        "This rule exists to stop the app punishing the hardest part of studying.",
    ),
    # ── breaks, offered before they are stolen ──────────────────────────────
    (
        "IF fatigue is high AND progress is stalled THEN break_offer is urge",
        0.9,
        "Tired and not moving is the moment a break is a repair rather than a reward. "
        "Offering it removes the need to steal one.",
    ),
    (
        "IF fatigue is high AND progress is strong THEN break_offer is mention",
        0.6,
        "Deep in it and tired: mention a break, do not push. Flow is worth more than "
        "the schedule.",
    ),
    (
        "IF fatigue is medium AND topic_match is low THEN break_offer is mention",
        0.7,
        "Drifting while tired is usually a break that was needed and not taken.",
    ),
    (
        "IF fatigue is low THEN break_offer is none",
        0.8,
        "Nobody needs a break twenty minutes in.",
    ),
    # ── asking to see the page, the only signal that costs the student ──────
    (
        "IF progress is stalled AND is_own_work is low AND fatigue is not low AND confidence is not low THEN ask_page is yes",
        0.8,
        "Nothing on screen is theirs and nothing has moved — the case where the work "
        "may be happening on paper and we are simply blind to it. The fatigue clause is "
        "'not low' rather than 'medium' because a *very* tired student is the one most "
        "likely to have moved to paper, and 'medium' excluded them: membership in medium "
        "falls back to zero above 0.75, so the rule could never fire for the case it was "
        "written for.",
    ),
    (
        "IF progress is strong THEN ask_page is no",
        1.0,
        "Progress is already proven. Asking anyway spends an interruption on something "
        "we know, which is the rule the whole intrusion policy turns on.",
    ),
    (
        "IF is_own_work is high THEN ask_page is no",
        0.85,
        "Their writing is visible on screen and already being read. No need to ask.",
    ),
]


def default_rules() -> list[Rule]:
    """Parse the shipped rule base. Raises on a malformed rule, loudly and early."""
    rules: list[Rule] = []
    for index, (text, weight, because) in enumerate(DEFAULT_RULES, start=1):
        rule = parse_rule(text, rule_id=f"r{index:02d}", weight=weight, because=because)
        rules.append(rule)
    return rules


def validate(rules: list[Rule]) -> list[str]:
    """Problems a reader would want told about, rather than discovering at runtime.

    A rule naming a variable or word that does not exist can never fire, and a rule
    base that silently contains one is a rule base nobody can trust.
    """
    problems: list[str] = []
    known = {**PERCEPTS, **DECISIONS}
    for rule in rules:
        for clause in rule.when:
            variable = known.get(clause.variable)
            if variable is None:
                problems.append(f"{rule.id}: no such percept {clause.variable!r}")
            elif variable.set_named(clause.set_name) is None:
                options = ", ".join(fuzzy_set.name for fuzzy_set in variable.sets)
                problems.append(
                    f"{rule.id}: {clause.variable!r} has no word {clause.set_name!r} (has: {options})"
                )
        decision = DECISIONS.get(rule.then_variable)
        if decision is None:
            problems.append(f"{rule.id}: no such decision {rule.then_variable!r}")
        elif decision.set_named(rule.then_set) is None:
            options = ", ".join(fuzzy_set.name for fuzzy_set in decision.sets)
            problems.append(
                f"{rule.id}: {rule.then_variable!r} has no word {rule.then_set!r} (has: {options})"
            )
    return problems
