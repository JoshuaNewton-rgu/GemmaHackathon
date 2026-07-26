"""Reading a photograph of handwritten notes.

The work-diff was device-independent but not *medium*-independent: it could only see
a file. A student working on paper produced an empty diff and looked, to the app,
exactly like a student doing nothing — the worst possible failure for a tool whose
whole claim is that it measures real progress.

The fix is to turn the page into text and then change nothing else. A transcription
is stored as an artifact snapshot like any other, so `judge_delta` compares two
photos of a notebook the same way it compares two saves of a markdown file, and the
receipt and learner model need no notion of paper at all.
"""

from __future__ import annotations

from typing import Any

from .. import prompts
from ..providers import CallMeta, Provider
from ..schemas import Contract, PageRead

#: Pseudo-path under which page transcriptions are snapshotted. The `paper:` prefix
#: keeps them from ever colliding with a real file on disk.
PAPER_PATH = "paper:notes"


def transcribe_page(provider: Provider, contract: Contract, image: Any) -> tuple[PageRead, CallMeta]:
    """Read a photo of a page. Never grades it — that is the diff's job, later."""
    raw, meta = provider.complete_json(
        prompts.render(prompts.PAGE_READ, contract=contract.for_prompt()),
        image=image,
        max_tokens=1200,  # a full side of notes is a lot of tokens
    )

    if not meta.ok:
        page = PageRead(text="", legible=False, page_note=meta.error or "model call failed")
        page._repairs.append("model call failed")
        return page, meta

    page = PageRead.from_model(raw)
    page._meta = meta.to_dict()
    meta.repairs = list(page._repairs)
    return page, meta


def unreadable_reason(page: PageRead) -> str | None:
    """A kind, specific line to show when a photo cannot be used — or None if it can.

    Worth being precise rather than saying "try again": the student is standing there
    holding a notebook, and "a bit closer, and turn a light on" is actionable in a way
    that a generic failure is not.
    """
    if not page.looks_like_notes:
        return "That does not look like a page of notes — no harm done, try again when you have one."
    if not page.legible or not page.text.strip():
        return "Too dark or too far away to read. A bit closer, with the page flat, and I will get it."
    return None
