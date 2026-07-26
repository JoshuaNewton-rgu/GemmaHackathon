"""Deterministic study evidence and scoring for the first ProofStudy layer."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from .schemas import ProgressComponents, ProgressScore

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'-]*")
_STOP_WORDS = {
    "a", "about", "after", "again", "all", "also", "am", "an", "and", "any", "are", "as", "at",
    "be", "because", "been", "before", "being", "but", "by", "can", "could", "did", "do", "does",
    "doing", "for", "from", "had", "has", "have", "he", "her", "here", "him", "his", "how", "i",
    "if", "in", "into", "is", "it", "its", "just", "may", "more", "most", "my", "no", "not", "of",
    "on", "or", "our", "out", "over", "same", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "them", "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who",
    "will", "with", "would", "you", "your",
}


def _words(text: str) -> list[str]:
    return [match.group(0).lower().strip("-'") for match in _WORD.finditer(text)]


def extract_keywords(text: str, *, limit: int = 12) -> list[str]:
    """Return stable keywords ordered by frequency, then first appearance."""
    if limit <= 0:
        return []
    words = [word for word in _words(text) if len(word) >= 3 and word not in _STOP_WORDS]
    counts = Counter(words)
    first = {word: words.index(word) for word in counts}
    return sorted(counts, key=lambda word: (-counts[word], first[word], word))[:limit]


def extract_concepts(text: str, *, limit: int = 12) -> list[str]:
    """Extract useful one- and two-word concepts without a model call.

    Repeated adjacent content words become phrases; remaining high-signal words
    fill the list.  The result is deterministic and suitable for score evidence.
    """
    if limit <= 0:
        return []
    tokens = _words(text)
    content = [word if len(word) >= 3 and word not in _STOP_WORDS else "" for word in tokens]
    phrases = [
        f"{left} {right}"
        for left, right in zip(content, content[1:])
        if left and right and left != right
    ]
    phrase_counts = Counter(phrases)
    first_phrase = {phrase: phrases.index(phrase) for phrase in phrase_counts}
    ranked_phrases = sorted(
        phrase_counts,
        key=lambda phrase: (-phrase_counts[phrase], first_phrase[phrase], phrase),
    )
    result = ranked_phrases[:limit]
    for keyword in extract_keywords(text, limit=limit):
        if keyword not in result:
            result.append(keyword)
        if len(result) == limit:
            break
    return result


def _new_items(current: Iterable[str], previous: Iterable[str]) -> list[str]:
    old = {item.casefold() for item in previous}
    return [item for item in current if item.casefold() not in old]


def calculate_level(xp: int, *, xp_per_level: int = 100) -> int:
    """Levels are one-indexed and advance every fixed XP band."""
    if xp_per_level < 1:
        raise ValueError("xp_per_level must be positive")
    return max(0, int(xp)) // xp_per_level + 1


def compute_progress_score(
    *,
    elapsed_min: float = 0,
    planned_duration_min: float = 1,
    completion_ratio: float | None = None,
    previous_text: str = "",
    current_text: str = "",
    diff_verdict: str = "stalled",
    substantive: bool | None = None,
    word_growth: int | None = None,
    new_concept_count: int | None = None,
) -> ProgressScore:
    """Calculate a transparent 0–100 progress score.

    Weights are intentionally visible: completion 35, substantive net word
    growth 30, newly observed concepts 20, and the diff verdict 15.
    """
    planned = max(1.0, float(planned_duration_min))
    ratio = float(elapsed_min) / planned if completion_ratio is None else float(completion_ratio)
    ratio = max(0.0, min(1.0, ratio))
    completion_points = round(35 * ratio)

    previous_words = _words(previous_text)
    current_words = _words(current_text)
    net_growth = max(
        0,
        int(word_growth) if word_growth is not None else len(current_words) - len(previous_words),
    )
    if substantive is None:
        substantive = diff_verdict == "progress" or net_growth >= 8
    substantive_growth = net_growth if substantive else 0
    word_points = round(30 * min(1.0, substantive_growth / 100.0))

    old_concepts = extract_concepts(previous_text)
    concepts = extract_concepts(current_text)
    new_concepts = _new_items(concepts, old_concepts)
    concept_count = len(new_concepts) if new_concept_count is None else max(0, int(new_concept_count))
    concept_points = round(20 * min(1.0, concept_count / 5.0))

    verdict = diff_verdict.strip().lower()
    verdict_points = {"progress": 15, "padding": 3, "stalled": 0}.get(verdict, 0)
    components = ProgressComponents(
        completion=completion_points,
        word_growth=word_points,
        new_concepts=concept_points,
        diff_verdict=verdict_points,
    )
    return ProgressScore(
        score=components.total,
        components=components,
        completion_ratio=ratio,
        substantive_word_growth=substantive_growth,
        concepts=concepts,
        new_concepts=new_concepts,
        diff_verdict=verdict if verdict in {"progress", "padding", "stalled"} else "stalled",
    )


# Compatibility names for callers that use "calculate" or a shorter noun.
calculate_progress = compute_progress_score
progress_score = compute_progress_score
level_for_xp = calculate_level
