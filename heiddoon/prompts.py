"""Every prompt in the product, in one file, with a version stamp.

Prompts are the largest lever on eval accuracy and the easiest thing to change by
accident. `PROMPT_VERSION` is written into every eval result so a number can always
be traced back to the wording that produced it — otherwise "we scored 13/15" is an
unfalsifiable claim about a file that has since been edited.
"""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "2026-07-26.1"


CONTRACT_COMPILER = """A student is starting a study session and has described it in their own words.
Compile it into this exact schema:

{{"task": str,               // the specific thing they are studying
  "why": str,                // their own stated reason it matters, in their words; "" if not given
  "allowed": [str],          // kinds of content that count as on-task for THEM
  "blocked": [str],          // kinds of content that count as drift
  "artifacts": [str],        // file names/paths whose progress should be tracked
  "signals": [str],          // any of: screen, camera, diff, idle
  "tone": str,               // how they want to be spoken to, e.g. kind_but_sharp
  "ends": str}}              // clock time the session ends, "" if not given

Rules:
- Take their rules literally. Do not add restrictions they did not ask for, and do not
  soften ones they did. These are their rules, not yours.
- "allowed" and "blocked" describe MEANING, not websites. "lecture videos about the
  contracted topic" is a good entry; "youtube.com" is not.
- Only include a signal if they asked for it or clearly implied it.

Their words: {text}"""


VERDICT = """You are a focus companion for a student. They wrote this contract for themselves:
{contract}

Judge the attached frame against that contract. The frame is either a SCREEN capture
or a WEBCAM photo of the student — work out which.

How to judge:
- Judge MEANING, not the app or website. The same site can be on-task or off-task.
  A lecture about the contracted topic on a video site is ON task. Entertainment on
  that same site is OFF task.
- A document or PDF is ON task only if its subject matches the contracted task. A
  well-made PDF for a different module is still drift.
- A messaging app is ON task only if the visible conversation is about the coursework.
- Webcam: working at the desk is ON task. Phone in hand, or an empty chair, is OFF task.
- Judge only what you can actually see. If the frame is ambiguous, unreadable, or
  mostly empty, say so and set confidence "low" and on_task true — a wrong accusation
  costs far more trust than a missed drift.

If they are off task, write ONE nudge line: warm, short, no shame, no exclamation
marks, no questions. Where it fits naturally, use their own stated reason ("why") back
to them rather than any instruction of your own.

Schema:
{{"frame_kind": "screen"|"camera",
  "on_task": true|false,
  "seen": str,          // what is actually in the frame, concretely
  "reason": str,        // one line: why that is or is not on task for THIS contract
  "nudge": str,         // the line, or "" if on task
  "confidence": "low"|"medium"|"high"}}"""


ARTIFACT_DIFF = """Two snapshots of a student's working file, taken {minutes} minutes apart.
Their contract: {contract}

Judge the DELTA only — what changed between BEFORE and AFTER. Ignore the unchanged parts
except as context for whether the new material is any good.

What counts as what:
- "progress": genuinely new substance. Worked examples, derivations, definitions,
  corrections, real structure.
- "padding": text was added but it carries no new understanding. Restatement, filler,
  repetition, vague promises to study later, words that would not help them in an exam.
- "stalled": nothing meaningful changed, or the file shrank without improving.

Be specific in quality_note: name the actual gap or the actual good step, so the student
learns something from reading it. Do not praise word count.

Schema:
{{"delta_words": int,        // approximate net words added
  "substantive": true|false,
  "summary": str,            // one line on what changed
  "quality_note": str,       // one specific observation about the new content
  "verdict": "progress"|"padding"|"stalled"}}

--- BEFORE ---
{before}

--- AFTER ---
{after}"""


BOUNCER_QUESTION = """A student wants a break. Before they get it, they answer one question
from their own notes — recalling it is worth more than rereading it.

Write ONE question that:
- can be answered from the notes below, in two or three sentences from memory
- targets something that matters (a mechanism, a distinction, a common trap), not a
  definition they could parrot
- does not quote the answer back in the question

Notes:
{notes}

Schema: {{"question": str, "key_points": [str]}}   // key_points: what a correct answer must contain"""


BOUNCER_GRADE = """Grade a student's recall answer.

Question: {question}
A correct answer must contain: {key_points}
They answered: "{answer}"

Grade honestly but generously about form: reward the idea, not the phrasing, and give
partial credit when the core mechanism is right. Do not pass an answer that is empty,
off-topic, or an attempt to skip the question. Feedback is one warm line — if they got
it wrong, the line should teach the missing piece, not scold.

Schema: {{"pass": true|false, "feedback": str, "matched_points": [str]}}"""


RECEIPT = """A study session just ended. Here is what actually happened, in order:
{events}

What Heid Doon knew about this student before today:
{learner}

Write their receipt.

1. autopsy — two sentences. Name the PATTERN and its TRIGGER, not the incidents
   ("you drift about 25 minutes in, right after the derivations — that is task
   aversion, not distraction"). No shame, no praise-sandwich, no advice yet. If the
   log is too short to support a pattern, say that plainly instead of inventing one.
2. learner_model — the updated model, same schema as above. Only change fields the
   log gives you evidence for; carry the rest over unchanged.
3. tomorrow — one line of plan that puts the hard material BEFORE the drift window
   you identified, with a break already scheduled so there is nothing to steal.
4. focus_score — 0-100, based on the ratio of on-task check-ins and whether the
   artifact actually moved. A session with real progress should not score low because
   of one lapse.

Schema:
{{"autopsy": str,
  "tomorrow": str,
  "focus_score": int,
  "learner_model": {{"weak_topics": [str], "strong_topics": [str], "drift_patterns": [str],
                     "avg_focus_streak_min": int, "best_nudge_style": str,
                     "next_difficulty": "easier"|"same"|"harder"}}}}"""


def render(template: str, **values: Any) -> str:
    """Fill a template, JSON-encoding any dict or list argument."""
    encoded = {
        key: json.dumps(value, ensure_ascii=False, indent=None) if isinstance(value, (dict, list)) else value
        for key, value in values.items()
    }
    return template.format(**encoded)
