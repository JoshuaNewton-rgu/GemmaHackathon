"""The data contracts of Heid Doon.

Every mechanic in the product is a model call that must come back as one of these
shapes. Model output is untrusted: a small model under a 20-second cadence will
occasionally hand back a missing field, a string where an int belongs, or a list
where a scalar belongs. So each type coerces rather than raises — a session should
degrade, never crash — and records what had to be repaired in `_repairs` so the
eval harness can report prompt reliability honestly instead of hiding it.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

FrameKind = Literal["screen", "camera"]
DiffVerdict = Literal["progress", "padding", "stalled"]
Difficulty = Literal["easier", "same", "harder"]


# ── coercion helpers ────────────────────────────────────────────────────────
# Each takes whatever the model produced and returns a value of the right type,
# appending a note to `repairs` when it had to intervene.


def _str(value: Any, default: str, field_name: str, repairs: list[str]) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        repairs.append(f"{field_name}: missing")
        return default
    repairs.append(f"{field_name}: coerced {type(value).__name__} to str")
    return str(value)


def _bool(value: Any, default: bool, field_name: str, repairs: list[str]) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "on_task", "on-task", "1"):
            repairs.append(f"{field_name}: parsed str {value!r} as True")
            return True
        if lowered in ("false", "no", "off_task", "off-task", "0"):
            repairs.append(f"{field_name}: parsed str {value!r} as False")
            return False
    if value is None:
        repairs.append(f"{field_name}: missing")
        return default
    repairs.append(f"{field_name}: coerced {type(value).__name__} to bool")
    return bool(value)


def _int(value: Any, default: int, field_name: str, repairs: list[str]) -> int:
    if isinstance(value, bool):  # bool is an int subclass; almost never intended
        repairs.append(f"{field_name}: got bool, using default")
        return default
    if isinstance(value, int):
        return value
    try:
        coerced = int(float(str(value).strip()))
    except (TypeError, ValueError):
        repairs.append(f"{field_name}: unparseable {value!r}")
        return default
    repairs.append(f"{field_name}: coerced {type(value).__name__} to int")
    return coerced


def _str_list(value: Any, field_name: str, repairs: list[str]) -> list[str]:
    if isinstance(value, list):
        return [item.strip() if isinstance(item, str) else str(item) for item in value if item is not None]
    if value is None:
        repairs.append(f"{field_name}: missing")
        return []
    if isinstance(value, str):
        # A very common small-model slip: a comma-joined string instead of a list.
        repairs.append(f"{field_name}: split str into list")
        return [part.strip() for part in value.split(",") if part.strip()]
    repairs.append(f"{field_name}: coerced {type(value).__name__} to list")
    return [str(value)]


def _enum(value: Any, allowed: tuple[str, ...], default: str, field_name: str, repairs: list[str]) -> str:
    if isinstance(value, str) and value.strip().lower() in allowed:
        return value.strip().lower()
    repairs.append(f"{field_name}: {value!r} not in {allowed}, using {default!r}")
    return default


@dataclass
class _Base:
    """Shared plumbing: repair tracking, call metadata, dict round-tripping."""

    _repairs: list[str] = field(default_factory=list, repr=False)
    _meta: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def clean(self) -> bool:
        """True when the model produced this shape without any repair."""
        return not self._repairs

    def to_dict(self, include_internals: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_internals:
            data.pop("_repairs", None)
            data.pop("_meta", None)
        return data


# ── the contracts ───────────────────────────────────────────────────────────


@dataclass
class Contract(_Base):
    """The student's own rules. Everything downstream is judged against this."""

    task: str = ""
    why: str = ""
    allowed: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    tone: str = "kind_but_sharp"
    ends: str = ""

    @classmethod
    def from_model(cls, raw: dict[str, Any]) -> Contract:
        repairs: list[str] = []
        return cls(
            task=_str(raw.get("task"), "", "task", repairs),
            # `why` is ours, not the notebook's: nudges quote the student's own
            # reason back at them, which is the whole autonomy mechanic.
            why=_str(raw.get("why", ""), "", "why", repairs),
            allowed=_str_list(raw.get("allowed"), "allowed", repairs),
            blocked=_str_list(raw.get("blocked"), "blocked", repairs),
            artifacts=_str_list(raw.get("artifacts"), "artifacts", repairs),
            signals=_str_list(raw.get("signals"), "signals", repairs),
            tone=_str(raw.get("tone"), "kind_but_sharp", "tone", repairs),
            ends=_str(raw.get("ends"), "", "ends", repairs),
            _repairs=repairs,
        )

    def for_prompt(self) -> dict[str, Any]:
        """The subset worth spending context tokens on when judging a frame."""
        return {
            "task": self.task,
            "why_it_matters": self.why,
            "allowed": self.allowed,
            "blocked": self.blocked,
            "tone": self.tone,
        }


@dataclass
class Verdict(_Base):
    """One judged frame — screen or camera."""

    frame_kind: str = "screen"
    on_task: bool = True
    seen: str = ""
    reason: str = ""
    nudge: str = ""
    confidence: str = "medium"
    #: The student's own visible writing, read out of the same frame. This is what
    #: makes progress and retrieval questions work with no file configured — the
    #: screen is already being captured, so reading it costs one field, not one call.
    work_text: str = ""
    work_source: str = ""

    @classmethod
    def from_model(cls, raw: dict[str, Any]) -> Verdict:
        repairs: list[str] = []
        # Default to ON task when the model is unintelligible. A false nudge is
        # worse than a missed one: it trains the student to distrust the app,
        # and distrust gets it uninstalled.
        return cls(
            frame_kind=_enum(raw.get("frame_kind"), ("screen", "camera"), "screen", "frame_kind", repairs),
            on_task=_bool(raw.get("on_task"), True, "on_task", repairs),
            seen=_str(raw.get("seen"), "", "seen", repairs),
            reason=_str(raw.get("reason"), "", "reason", repairs),
            nudge=_str(raw.get("nudge", ""), "", "nudge", repairs),
            confidence=_enum(raw.get("confidence", "medium"), ("low", "medium", "high"), "medium", "confidence", repairs),
            work_text=_str(raw.get("work_text", ""), "", "work_text", repairs),
            work_source=_str(raw.get("work_source", ""), "", "work_source", repairs),
            _repairs=repairs,
        )


@dataclass
class Diff(_Base):
    """A judged delta between two snapshots of the contracted artifact.

    The differentiator: progress read from the work, not from surveilled activity.
    """

    delta_words: int = 0
    substantive: bool = False
    summary: str = ""
    quality_note: str = ""
    verdict: str = "stalled"

    @classmethod
    def from_model(cls, raw: dict[str, Any]) -> Diff:
        repairs: list[str] = []
        return cls(
            delta_words=_int(raw.get("delta_words"), 0, "delta_words", repairs),
            substantive=_bool(raw.get("substantive"), False, "substantive", repairs),
            summary=_str(raw.get("summary"), "", "summary", repairs),
            quality_note=_str(raw.get("quality_note"), "", "quality_note", repairs),
            verdict=_enum(
                raw.get("verdict"), ("progress", "padding", "stalled"), "stalled", "verdict", repairs
            ),
            _repairs=repairs,
        )


@dataclass
class PageRead(_Base):
    """A photo of handwritten notes, turned into text.

    Transcribing rather than judging is deliberate: once the page is text, the work
    diff treats paper exactly like a file, so progress/padding/stalled, the receipt
    and the learner model all work on handwriting with no special cases.
    """

    text: str = ""
    legible: bool = False
    page_note: str = ""
    looks_like_notes: bool = True

    @classmethod
    def from_model(cls, raw: dict[str, Any]) -> PageRead:
        repairs: list[str] = []
        text = _str(raw.get("text"), "", "text", repairs)
        page = cls(
            text=text,
            # A model that returned no text has not read a legible page, whatever
            # it claims in the flag.
            legible=_bool(raw.get("legible"), bool(text.strip()), "legible", repairs) and bool(text.strip()),
            page_note=_str(raw.get("page_note"), "", "page_note", repairs),
            looks_like_notes=_bool(raw.get("looks_like_notes", True), True, "looks_like_notes", repairs),
            _repairs=repairs,
        )
        return page


@dataclass
class Quiz(_Base):
    """A retrieval question generated from the student's own notes."""

    question: str = ""
    key_points: list[str] = field(default_factory=list)
    #: Where the question came from, shown to the student. A question built from the
    #: topic rather than from their writing must not claim to be "from your notes".
    source: str = "your own notes"

    @classmethod
    def from_model(cls, raw: dict[str, Any]) -> Quiz:
        repairs: list[str] = []
        return cls(
            question=_str(raw.get("question"), "", "question", repairs),
            key_points=_str_list(raw.get("key_points"), "key_points", repairs),
            _repairs=repairs,
        )


@dataclass
class Grade(_Base):
    """The Bouncer's ruling on a break request."""

    passed: bool = False
    feedback: str = ""
    matched_points: list[str] = field(default_factory=list)

    @classmethod
    def from_model(cls, raw: dict[str, Any]) -> Grade:
        repairs: list[str] = []
        # "pass" is a Python keyword, so the wire name and the field name differ.
        return cls(
            passed=_bool(raw.get("pass", raw.get("passed")), False, "pass", repairs),
            feedback=_str(raw.get("feedback"), "", "feedback", repairs),
            matched_points=_str_list(raw.get("matched_points", []), "matched_points", repairs),
            _repairs=repairs,
        )

    def to_dict(self, include_internals: bool = False) -> dict[str, Any]:
        data = super().to_dict(include_internals)
        data["pass"] = data.pop("passed")
        return data


@dataclass
class LearnerModel(_Base):
    """What Heid Doon has learned about this student. Persists across sessions."""

    weak_topics: list[str] = field(default_factory=list)
    strong_topics: list[str] = field(default_factory=list)
    drift_patterns: list[str] = field(default_factory=list)
    avg_focus_streak_min: int = 0
    best_nudge_style: str = "warm"
    next_difficulty: str = "same"

    @classmethod
    def from_model(cls, raw: dict[str, Any]) -> LearnerModel:
        repairs: list[str] = []
        return cls(
            weak_topics=_str_list(raw.get("weak_topics"), "weak_topics", repairs),
            strong_topics=_str_list(raw.get("strong_topics"), "strong_topics", repairs),
            drift_patterns=_str_list(raw.get("drift_patterns"), "drift_patterns", repairs),
            avg_focus_streak_min=_int(raw.get("avg_focus_streak_min"), 0, "avg_focus_streak_min", repairs),
            best_nudge_style=_str(raw.get("best_nudge_style"), "warm", "best_nudge_style", repairs),
            next_difficulty=_enum(
                raw.get("next_difficulty"), ("easier", "same", "harder"), "same", "next_difficulty", repairs
            ),
            _repairs=repairs,
        )


@dataclass
class Receipt(_Base):
    """The session's honest accounting: autopsy, updated learner model, tomorrow."""

    autopsy: str = ""
    tomorrow: str = ""
    focus_score: int = 0
    learner_model: LearnerModel = field(default_factory=LearnerModel)

    @classmethod
    def from_model(cls, raw: dict[str, Any]) -> Receipt:
        repairs: list[str] = []
        nested = raw.get("learner_model")
        if not isinstance(nested, dict):
            repairs.append("learner_model: missing or not an object")
            nested = {}
        learner = LearnerModel.from_model(nested)
        repairs.extend(f"learner_model.{note}" for note in learner._repairs)
        score = _int(raw.get("focus_score"), 0, "focus_score", repairs)
        if not 0 <= score <= 100:
            repairs.append(f"focus_score: {score} out of range, clamped")
            score = max(0, min(100, score))
        return cls(
            autopsy=_str(raw.get("autopsy"), "", "autopsy", repairs),
            tomorrow=_str(raw.get("tomorrow"), "", "tomorrow", repairs),
            focus_score=score,
            learner_model=learner,
            _repairs=repairs,
        )

    def to_dict(self, include_internals: bool = False) -> dict[str, Any]:
        data = super().to_dict(include_internals)
        data["learner_model"] = self.learner_model.to_dict(include_internals)
        return data


# ── ProofStudy MVP contracts ────────────────────────────────────────────────


@dataclass
class StudyMetadata(_Base):
    """The small, user-selected description of a study session."""

    subject: str = ""
    planned_duration_min: int = 25
    persona_id: str = "scottish_granny"
    due_date: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StudyMetadata:
        repairs: list[str] = []
        duration = _int(raw.get("planned_duration_min"), 25, "planned_duration_min", repairs)
        if duration < 5:
            repairs.append("planned_duration_min: below minimum, using 5")
            duration = 5
        elif duration > 120:
            repairs.append("planned_duration_min: above maximum, using 120")
            duration = 120
        raw_due_date = raw.get("due_date")
        due_date = "" if raw_due_date in (None, "") else _str(raw_due_date, "", "due_date", repairs)
        if due_date:
            try:
                date.fromisoformat(due_date)
            except ValueError:
                repairs.append("due_date: expected YYYY-MM-DD, ignoring invalid value")
                due_date = ""
        return cls(
            subject=_str(raw.get("subject"), "", "subject", repairs),
            planned_duration_min=duration,
            persona_id=_str(raw.get("persona_id"), "scottish_granny", "persona_id", repairs),
            due_date=due_date,
            _repairs=repairs,
        )


@dataclass
class ProgressComponents(_Base):
    """Point contributions to a progress score; the fields sum to ``total``."""

    completion: int = 0
    word_growth: int = 0
    new_concepts: int = 0
    diff_verdict: int = 0

    @property
    def total(self) -> int:
        return self.completion + self.word_growth + self.new_concepts + self.diff_verdict

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ProgressComponents:
        return cls(
            completion=max(0, min(35, int(raw.get("completion", 0)))),
            word_growth=max(0, min(30, int(raw.get("word_growth", 0)))),
            new_concepts=max(0, min(20, int(raw.get("new_concepts", 0)))),
            diff_verdict=max(0, min(15, int(raw.get("diff_verdict", 0)))),
        )


@dataclass
class ProgressScore(_Base):
    """A transparent 0–100 score and the evidence used to calculate it."""

    score: int = 0
    components: ProgressComponents = field(default_factory=ProgressComponents)
    completion_ratio: float = 0.0
    substantive_word_growth: int = 0
    concepts: list[str] = field(default_factory=list)
    new_concepts: list[str] = field(default_factory=list)
    diff_verdict: str = "stalled"

    def __post_init__(self) -> None:
        self.score = max(0, min(100, int(self.score)))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ProgressScore:
        nested = raw.get("components", {})
        components = ProgressComponents.from_dict(nested if isinstance(nested, dict) else {})
        return cls(
            score=int(raw.get("score", components.total)),
            components=components,
            completion_ratio=max(0.0, min(1.0, float(raw.get("completion_ratio", 0.0)))),
            substantive_word_growth=max(0, int(raw.get("substantive_word_growth", 0))),
            concepts=[str(item) for item in raw.get("concepts", [])],
            new_concepts=[str(item) for item in raw.get("new_concepts", [])],
            diff_verdict=str(raw.get("diff_verdict", "stalled")),
        )

    def to_dict(self, include_internals: bool = False) -> dict[str, Any]:
        data = super().to_dict(include_internals)
        data["components"] = self.components.to_dict(include_internals)
        return data


@dataclass
class QuizQuestion(_Base):
    id: str = ""
    question: str = ""
    answer: str = ""
    concept: str = ""
    kind: str = "recall"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> QuizQuestion:
        return cls(
            id=str(raw.get("id", "")).strip(),
            question=str(raw.get("question", "")).strip(),
            answer=str(
                raw.get(
                    "answer",
                    raw.get("expected_answer", " ".join(str(item) for item in raw.get("key_points", []))),
                )
            ).strip(),
            concept=str(raw.get("concept", "")).strip(),
            kind=str(raw.get("kind", "recall")).strip(),
        )


@dataclass
class QuizSet(_Base):
    """A ProofStudy retrieval set. MVP sets always contain five questions."""

    questions: list[QuizQuestion] = field(default_factory=list)
    subject: str = ""
    source: str = "your own notes"

    def __post_init__(self) -> None:
        if len(self.questions) != 5:
            raise ValueError("a quiz set must contain exactly 5 questions")

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> QuizSet:
        questions = [
            item if isinstance(item, QuizQuestion) else QuizQuestion.from_dict(item)
            for item in raw.get("questions", [])
            if isinstance(item, (dict, QuizQuestion))
        ]
        return cls(
            questions=questions,
            subject=str(raw.get("subject", "")).strip(),
            source=str(raw.get("source", "your own notes")).strip(),
        )


@dataclass
class QuizResult(_Base):
    """The answers and outcome for one five-question attempt."""

    answers: list[str] = field(default_factory=list)
    correct: list[bool] = field(default_factory=list)
    score: int = 0
    feedback: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.answers) != 5 or len(self.correct) != 5:
            raise ValueError("a quiz result must contain exactly 5 answers and 5 verdicts")
        self.score = max(0, min(100, int(self.score)))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> QuizResult:
        correct = [bool(item) for item in raw.get("correct", [])]
        score = raw.get("score", round(sum(correct) * 20))
        return cls(
            answers=[str(item) for item in raw.get("answers", [])],
            correct=correct,
            score=int(score),
            feedback=[str(item) for item in raw.get("feedback", [])],
        )


@dataclass
class CoachFeedback(_Base):
    message: str = ""
    strengths: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    persona_id: str = "scottish_granny"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CoachFeedback:
        return cls(
            message=str(raw.get("message", "")).strip(),
            strengths=[str(item) for item in raw.get("strengths", [])],
            next_steps=[str(item) for item in raw.get("next_steps", [])],
            persona_id=str(raw.get("persona_id", "scottish_granny")),
        )


@dataclass
class GamificationState(_Base):
    xp: int = 0
    level: int = 1
    streak_days: int = 0
    last_study_date: str | None = None

    def __post_init__(self) -> None:
        self.xp = max(0, int(self.xp))
        self.level = max(1, int(self.level))
        self.streak_days = max(0, int(self.streak_days))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> GamificationState:
        return cls(
            xp=raw.get("xp", 0),
            level=raw.get("level", 1),
            streak_days=raw.get("streak_days", 0),
            last_study_date=raw.get("last_study_date"),
        )


# Descriptive compatibility names used by early ProofStudy callers.
ProgressBreakdown = ProgressComponents
StudyProgress = ProgressScore
QuizAttemptResult = QuizResult


@dataclass
class Event:
    """One thing that happened in a session. The receipt is generated from these.

    Deliberately narrow: an event holds a verdict's *conclusion*, never a frame.
    Frames are judged and dropped, so there is no code path that can persist one.
    """

    kind: str  # screen | camera | diff | quiz | idle | session
    at: float = field(default_factory=time.time)
    on_task: bool | None = None
    seen: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def for_prompt(self, session_start: float) -> dict[str, Any]:
        """Compact, relative-time form for the receipt prompt."""
        minutes = int((self.at - session_start) // 60)
        compact: dict[str, Any] = {"t": f"+{minutes:02d}m", "kind": self.kind}
        if self.on_task is not None:
            compact["on_task"] = self.on_task
        if self.seen:
            compact["seen"] = self.seen
        compact.update(self.detail)
        return compact
