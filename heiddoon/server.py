"""The web app: one HTTP surface over the same Session the watcher uses.

Deliberately not a second implementation of the loop. The previous version had the
mechanics in notebook cells and the UI in Gradio callbacks holding their own state,
which meant the demo and the product could disagree. Here every route delegates to
`Session`, so anything the UI shows has been through the same code path — and is in
the database — as anything the local watcher recorded.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import queue
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import prompts
from .config import settings
from .core.contract import compile_contract
from .autopilot import Autopilot
from .core import notes as notes_mod
from .fuzzy import DECISIONS, PERCEPTS, validate
from .core.session import Session
from .personas import list_personas, resolve_persona_id
from .providers import Provider, ProviderError, get_provider
from .schemas import Contract, Event, StudyMetadata
from .store import SessionGone, Store

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="ProofStudy", version="0.2.0")

_store = Store(settings.db_path)
_sessions: dict[int, Session] = {}
_streams: dict[int, list[queue.SimpleQueue]] = {}
_autopilot = Autopilot()


@app.exception_handler(SessionGone)
async def _session_gone(request, exc: SessionGone) -> JSONResponse:
    """A vanished session is the client's problem to recover from, not a crash.

    Drops the stale in-memory session so a retry cannot hit the same wall, and
    answers 409 with something the UI can act on.
    """
    for session_id in list(_sessions):
        if not _store.get_session(session_id):
            _sessions.pop(session_id, None)
            _streams.pop(session_id, None)
    return JSONResponse(
        status_code=409,
        content={
            "detail": "That session no longer exists — the database may have been deleted or moved. "
            "Start a new session; nothing else is affected.",
            "session_gone": True,
        },
    )


def _provider() -> Provider:
    try:
        return get_provider()
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=f"model unavailable: {exc}") from exc


def _session(session_id: int) -> Session:
    """Fetch a live session, rehydrating from the database if this process restarted."""
    if session_id not in _sessions:
        try:
            session = Session.resume(_provider(), session_id, store=_store)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _attach_stream(session)
        _sessions[session_id] = session
    return _sessions[session_id]


def _attach_stream(session: Session) -> None:
    def publish(event: Event) -> None:
        for subscriber in _streams.get(session.id, []):
            subscriber.put(event.to_dict())

    _streams.setdefault(session.id, [])
    session.on_event(publish)


# ── models ──────────────────────────────────────────────────────────────────


class ContractRequest(BaseModel):
    text: str


class StartRequest(BaseModel):
    contract: dict[str, Any]
    profile: str = "default"
    study: dict[str, Any] | None = None


class DiffRequest(BaseModel):
    before: str
    after: str
    minutes: int = 20


class BreakRequest(BaseModel):
    notes: str | None = None


class AnswerRequest(BaseModel):
    answer: str = ""
    quiz_id: str = ""
    answers: list[dict[str, str]] = []


class TTSRequest(BaseModel):
    text: str
    voice: str | None = None
    style: str | None = None
    emotion: str | None = None
    speed: float | None = None


class AutopilotRequest(BaseModel):
    enabled: bool = True
    cadence_s: int | None = None


class BreakStateRequest(BaseModel):
    on_break: bool


class WeightRequest(BaseModel):
    rule_id: str
    weight: float


# ── status ──────────────────────────────────────────────────────────────────


def _privacy_line(reachable: bool, is_local: bool, is_mock: bool) -> str:
    """Say exactly what this configuration does with a frame. Never more.

    The privacy claim is the product's central argument, so it is generated from
    the running configuration rather than written into the page as copy — a
    hosted backend must never render the local-only promise.
    """
    if is_mock:
        return "Mock provider: no model runs and no frame is judged at all."
    if not reachable:
        return "No model configured — nothing is being judged."
    if is_local:
        return "Frames judged on this machine by a local model. Never stored, never sent."
    return "Frames are sent to a hosted API to be judged, then discarded. Never stored."


def _frame_payload(result: Any) -> dict[str, Any]:
    """One response shape for both decision paths.

    The interpretable path returns an Outcome carrying a rule trace; the binary path
    returns a Verdict. The UI should not have to care which is configured, so the
    difference is flattened here — with `trace` present only when there is one.
    """
    if hasattr(result, "decision"):  # Outcome, from the fuzzy path
        return {
            "verdict": {
                "on_task": result.on_task,
                "seen": result.perception.seen,
                "reason": result.perception.reason,
                "nudge": result.nudge_line,
                "confidence": result.perception.confidence,
                "work_text": result.perception.work_text,
                "work_source": result.perception.work_source,
            },
            "interpretable": True,
            "act": result.act,
            "firmness": result.firmness,
            "trace": result.decision.to_dict(),
            "repairs": result.repairs,
        }
    return {"verdict": result.to_dict(), "interpretable": False, "repairs": result._repairs}


def _server_capture_available() -> bool:
    """Can this process see a screen? False on a headless or remote host."""
    try:
        from .watchers import screen as screen_mod

        return screen_mod.available()
    except Exception:  # noqa: BLE001
        return False


def _should_use_piper_backend() -> bool:
    if not settings.tts_enabled:
        return False
    backend = (getattr(settings, "tts_backend", "auto") or "auto").lower()
    if backend == "hf":
        return False
    if backend == "piper":
        return True
    return bool(shutil.which("piper"))


def _synthesize_tts_with_piper(
    text: str,
    voice: str | None = None,
    style: str | None = None,
    emotion: str | None = None,
    speed: float | None = None,
) -> bytes:
    executable = getattr(settings, "tts_piper_executable", "piper") or "piper"
    model = getattr(settings, "tts_piper_model", "") or os.getenv("HEIDDOON_TTS_PIPER_MODEL", "")
    if not model:
        raise RuntimeError("Piper model not configured")
    if not shutil.which(executable):
        raise RuntimeError("Piper executable not found")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        output_path = Path(handle.name)

    try:
        subprocess.run(
            [executable, "--model", model, "--output_file", str(output_path)],
            input=text,
            text=True,
            capture_output=True,
            timeout=60,
            check=True,
        )
        return output_path.read_bytes()
    finally:
        output_path.unlink(missing_ok=True)


def _build_tts_payload(
    text: str,
    voice: str | None = None,
    style: str | None = None,
    emotion: str | None = None,
    speed: float | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"inputs": text, "voice": voice or settings.tts_voice}
    resolved_style = style or settings.tts_style or "neutral"
    resolved_emotion = emotion or settings.tts_emotion or "neutral"
    if resolved_style:
        payload["style"] = resolved_style
    if resolved_emotion:
        payload["emotion"] = resolved_emotion
    if speed is not None or settings.tts_speed != 1.0:
        payload["speed"] = speed if speed is not None else settings.tts_speed
    payload["instructions"] = (
        "Speak in a natural, human-like, conversational way with clear pauses. "
        f"Use a {resolved_style} tone and a {resolved_emotion} emotion."
    )
    return payload


def _synthesize_tts(
    text: str,
    voice: str | None = None,
    style: str | None = None,
    emotion: str | None = None,
    speed: float | None = None,
) -> bytes:
    if not settings.tts_enabled:
        raise RuntimeError("TTS is disabled")

    if _should_use_piper_backend():
        try:
            return _synthesize_tts_with_piper(text, voice, style, emotion, speed)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        else:
            last_error = None
    else:
        last_error = None

    payloads = [
        _build_tts_payload(text, voice, style, emotion, speed),
        {"inputs": text},
        {"inputs": text, "parameters": {"voice": voice or settings.tts_voice}},
    ]
    endpoint = settings.tts_endpoint or os.getenv("HEIDDOON_TTS_ENDPOINT") or f"https://router.huggingface.co/hf-inference/models/{settings.tts_model}"
    headers = {"Accept": "audio/*"}
    token = settings.hf_token or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if last_error is not None:
        payloads = [{"inputs": text}, {"inputs": text, "parameters": {"voice": voice or settings.tts_voice}}]

    for payload in payloads:
        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if response.content and content_type.startswith("audio/"):
                return response.content
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    if last_error is not None:
        raise RuntimeError(str(last_error)) from last_error
    raise RuntimeError("TTS synthesis failed")


@app.get("/api/status")
def status() -> dict[str, Any]:
    """What the UI needs to tell the truth about itself in its own header."""
    try:
        provider = get_provider()
        reachable, detail = True, f"{provider.model} via {provider.name}"
        is_local, is_mock = provider.is_local, provider.name == "mock"
    except ProviderError as exc:
        reachable, detail, is_local, is_mock = False, str(exc), False, False

    return {
        "provider_ready": reachable,
        "provider": detail,
        "local_inference": is_local,
        "mock": is_mock,
        # The UI must never claim privacy the configuration does not deliver, so
        # the banner text is decided here rather than in the browser.
        "privacy_line": _privacy_line(reachable, is_local, is_mock),
        "cadence_s": settings.cadence_s,
        "prompt_version": prompts.PROMPT_VERSION,
        # Whether the server can grab its own screen. When it can, the UI prefers
        # that over the browser's share-picker: one click and no dialog. It is only
        # the right frame because the server runs on the student's own machine —
        # which is also why the UI says whose screen it is about to read.
        "server_capture": _server_capture_available(),
        "auto_cadence_s": settings.auto_cadence_s,
        "notes_prompt_every_min": settings.notes_prompt_every_min,
    }


# ── contract ────────────────────────────────────────────────────────────────


@app.post("/api/contract/compile")
def api_compile_contract(request: ContractRequest) -> dict[str, Any]:
    contract, meta = compile_contract(_provider(), request.text)
    if not meta.ok:
        raise HTTPException(status_code=502, detail=f"could not compile the contract: {meta.error}")
    return {"contract": contract.to_dict(), "repairs": contract._repairs}


# ── session lifecycle ───────────────────────────────────────────────────────


@app.post("/api/session")
def api_start_session(request: StartRequest) -> dict[str, Any]:
    contract = Contract.from_model(request.contract)
    if not contract.task:
        raise HTTPException(status_code=400, detail="the contract needs a task")
    study = StudyMetadata.from_dict(
        request.study
        or {
            "subject": contract.task,
            "planned_duration_min": 45,
            "persona_id": contract.tone,
        }
    )
    study.subject = study.subject or contract.task
    study.persona_id = resolve_persona_id(study.persona_id)
    session = Session(_provider(), contract, store=_store, profile=request.profile, study=study)
    _attach_stream(session)
    _sessions[session.id] = session
    return {
        "session_id": session.id,
        "contract": contract.to_dict(),
        "study": session.study.to_dict(),
        "started_at": session.started_at,
        "planned_end_at": session.planned_end_at,
        "learner_model": session.learner.to_dict(),
        "gamification": _store.get_gamification(profile=request.profile).to_dict(),
    }


@app.get("/api/session/{session_id}")
def api_get_session(session_id: int) -> dict[str, Any]:
    session = _session(session_id)
    return {
        "session_id": session.id,
        "contract": session.contract.to_dict(),
        "study": session.study.to_dict(),
        "started_at": session.started_at,
        "planned_end_at": session.planned_end_at,
        "remaining_s": session.remaining_s,
        "has_notes_proof": session.has_notes_proof,
        "elapsed_min": session.elapsed_min,
        "events": [event.to_dict() for event in session.events],
        "learner_model": session.learner.to_dict(),
        "progress": (
            _store.latest_progress(session.id).to_dict()
            if _store.latest_progress(session.id)
            else None
        ),
        "gamification": _store.get_gamification(profile=session.profile).to_dict(),
    }


@app.post("/api/tts")
@app.post("/api/tss")
def api_tts(request: TTSRequest) -> Response:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    try:
        audio = _synthesize_tts(text, request.voice, request.style, request.emotion, request.speed)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"could not synthesize speech: {exc}") from exc
    return Response(content=audio, media_type="audio/wav")


@app.post("/api/session/{session_id}/finish")
async def api_finish(session_id: int) -> dict[str, Any]:
    session = _session(session_id)
    if not session.has_notes_proof:
        raise HTTPException(status_code=409, detail="upload a readable photo of your notes before finishing")
    # Stop watching before writing the receipt, so the loop cannot append an event
    # to a session that has already been accounted for.
    await _autopilot.stop(session_id)
    try:
        receipt, progress, gamification, coach = await asyncio.to_thread(session.finish_study)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _sessions.pop(session_id, None)
    return {
        "receipt": receipt.to_dict(),
        "progress": progress.to_dict(),
        "gamification": gamification.to_dict(),
        "coach": {"text": coach.message, "persona_id": coach.persona_id},
        "repairs": receipt._repairs,
    }


# ── the mechanics ───────────────────────────────────────────────────────────


@app.post("/api/session/{session_id}/frame")
async def api_frame(session_id: int, file: UploadFile, kind: str = "screen") -> dict[str, Any]:
    """Judge an uploaded frame.

    The bytes are decoded, judged and dropped inside this function. Nothing is
    written to disk, and `UploadFile`'s spool is closed on the way out — there is
    no path by which a frame survives this request.
    """
    from PIL import Image

    session = _session(session_id)
    if kind not in ("screen", "camera"):
        raise HTTPException(status_code=400, detail="kind must be 'screen' or 'camera'")

    payload = await file.read()
    try:
        with Image.open(io.BytesIO(payload)) as handle:
            frame = handle.convert("RGB")
    except Exception as exc:  # noqa: BLE001 - any decode failure is the same 400
        raise HTTPException(status_code=400, detail=f"could not read that image: {exc}") from exc
    finally:
        await file.close()

    result = await asyncio.to_thread(session.judge_frame, frame, kind=kind)
    return _frame_payload(result)


@app.post("/api/session/{session_id}/capture-screen")
async def api_capture_screen(session_id: int, monitor: int = 1) -> dict[str, Any]:
    """Capture this machine's screen server-side and judge it.

    The browser route (`getDisplayMedia`) is unavailable in embedded webviews and
    some browser configurations, where it throws NotSupportedError — and it makes
    the student pick a window from a dialog every single time. Since the server
    runs on the student's own machine, it can take the frame directly with the same
    code path the local watcher uses: one click, whole screen, no dialog.

    The frame lives in memory for the length of this call, exactly as with an
    upload. Nothing is written to disk.
    """
    from .watchers import screen as screen_mod

    session = _session(session_id)
    if not screen_mod.available():
        raise HTTPException(
            status_code=503,
            detail="Screen capture is unavailable on the server: pip install mss",
        )
    try:
        frame = await asyncio.to_thread(screen_mod.capture, monitor)
    except Exception as exc:  # noqa: BLE001 - no display, wrong monitor index, etc.
        raise HTTPException(status_code=503, detail=f"could not capture the screen: {exc}") from exc

    result = await asyncio.to_thread(session.judge_frame, frame, kind="screen")
    return _frame_payload(result)


@app.post("/api/session/{session_id}/autopilot")
async def api_autopilot(session_id: int, request: AutopilotRequest) -> dict[str, Any]:
    """Turn the automatic watch loop on or off.

    On is the intended state: the student should not have to press anything to be
    watched, and the loop runs server-side so it survives the tab being hidden.
    """
    session = _session(session_id)
    if request.enabled:
        state = await _autopilot.start(session, cadence_s=request.cadence_s)
        if state.last_error:
            raise HTTPException(status_code=503, detail=state.last_error)
    else:
        await _autopilot.stop(session_id)
    return {"autopilot": _autopilot.state(session_id).to_dict()}


@app.get("/api/session/{session_id}/autopilot")
def api_autopilot_state(session_id: int) -> dict[str, Any]:
    return {"autopilot": _autopilot.state(session_id).to_dict()}


@app.post("/api/session/{session_id}/notes-photo")
async def api_notes_photo(session_id: int, file: UploadFile) -> dict[str, Any]:
    """Read a photo of handwritten notes and judge the delta since the last one.

    This is the answer to paper: transcribe, then reuse the work-diff unchanged. An
    unreadable photo is not recorded as an event — holding a camera badly says
    nothing about whether the student is working.
    """
    from PIL import Image

    session = _session(session_id)
    payload = await file.read()
    try:
        with Image.open(io.BytesIO(payload)) as handle:
            frame = handle.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not read that image: {exc}") from exc
    finally:
        await file.close()

    page, diff = await asyncio.to_thread(session.check_notes_photo, frame)
    problem = notes_mod.unreadable_reason(page)
    progress = _store.latest_progress(session.id) if problem is None else None
    coach = (
        await asyncio.to_thread(
            session.coach_feedback,
            {
                "type": "notes_proof",
                "progress_score": progress.score,
                "new_concepts": progress.new_concepts,
                "subject": session.study.subject,
            },
        )
        if progress is not None
        else None
    )
    return {
        "ok": problem is None,
        "problem": problem,
        "page_note": page.page_note,
        "words": len(page.text.split()),
        "baseline": problem is None and diff is None,
        "diff": diff.to_dict() if diff else None,
        "progress": progress.to_dict() if progress else None,
        "coach": (
            {"text": coach.message, "persona_id": coach.persona_id}
            if coach
            else None
        ),
    }


@app.post("/api/session/{session_id}/break-state")
def api_break_state(session_id: int, request: BreakStateRequest) -> dict[str, Any]:
    """Tell the session a break started or ended, so it stops asking for anything."""
    session = _session(session_id)
    session.note_break(request.on_break)
    return {"on_break": request.on_break}


@app.post("/api/session/{session_id}/diff")
async def api_diff(session_id: int, request: DiffRequest) -> dict[str, Any]:
    session = _session(session_id)
    result = await asyncio.to_thread(
        session.judge_text_delta, request.before, request.after, minutes=request.minutes
    )
    return {"diff": result.to_dict(), "repairs": result._repairs}


@app.post("/api/session/{session_id}/artifact-check")
async def api_artifact_check(session_id: int) -> dict[str, Any]:
    """Diff the contracted file as it stands on disk right now."""
    session = _session(session_id)
    if not session.contract.artifacts:
        raise HTTPException(status_code=400, detail="this contract does not name an artifact to track")
    results = {}
    for artifact in session.contract.artifacts:
        result = await asyncio.to_thread(session.check_artifact, artifact)
        results[artifact] = result.to_dict() if result else None
    return {"diffs": results}


@app.post("/api/session/{session_id}/break")
async def api_break(session_id: int, request: BreakRequest) -> dict[str, Any]:
    session = _session(session_id)
    try:
        # Client-supplied notes are intentionally ignored. Quiz material comes only
        # from server-held excerpts attached to positive, on-contract verdicts.
        quiz_id, quiz = await asyncio.to_thread(session.request_break_set)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Expected answers remain only in the server-side pending set.
    return {
        "quiz_id": quiz_id,
        "questions": [
            {
                "id": question.id,
                "question": question.question,
                "kind": question.kind,
            }
            for question in quiz.questions
        ],
        "source": quiz.source,
    }


@app.post("/api/session/{session_id}/break/answer")
async def api_break_answer(session_id: int, request: AnswerRequest) -> dict[str, Any]:
    session = _session(session_id)
    if request.quiz_id:
        try:
            result, break_minutes, coach = await asyncio.to_thread(
                session.answer_break_set,
                request.quiz_id,
                [item.get("answer", "") for item in request.answers],
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        correct_count = sum(result.correct)
        return {
            "pass": correct_count >= 3,
            "correct_count": correct_count,
            "score": result.score,
            "feedback": " ".join(line for line in result.feedback if line),
            "question_feedback": result.feedback,
            "break_minutes": break_minutes,
            "coach": {"text": coach.message, "persona_id": coach.persona_id},
        }

    # Compatibility with the original single-question API.
    grade = await asyncio.to_thread(session.answer_break, request.answer)
    return {"pass": grade.passed, "feedback": grade.feedback, "matched_points": grade.matched_points}


# ── live event stream ───────────────────────────────────────────────────────


@app.get("/api/session/{session_id}/stream")
async def api_stream(session_id: int) -> StreamingResponse:
    """Server-sent events, so the UI shows the local watcher's verdicts too."""
    session = _session(session_id)
    subscriber: queue.SimpleQueue = queue.SimpleQueue()
    _streams.setdefault(session.id, []).append(subscriber)

    async def generator():
        try:
            while True:
                try:
                    event = subscriber.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.4)
                    # A comment frame keeps proxies from closing an idle stream.
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            subscribers = _streams.get(session.id, [])
            if subscriber in subscribers:
                subscribers.remove(subscriber)

    return StreamingResponse(generator(), media_type="text/event-stream")


# ── history ─────────────────────────────────────────────────────────────────


@app.get("/api/privacy")
def api_privacy(profile: str = "default") -> dict[str, Any]:
    """Everything the privacy screen states, generated from the live system.

    Deliberately not static copy. Each line is derived from the configuration and
    the database as they actually are, so the screen cannot promise a local-only
    guarantee while a hosted backend is answering.
    """
    try:
        provider = get_provider()
        is_local, is_mock, model = provider.is_local, provider.name == "mock", f"{provider.model}"
    except ProviderError:
        is_local, is_mock, model = False, False, "none configured"

    counts = _store.counts(profile=profile)

    if is_mock:
        lede = (
            "The mock provider is configured, so no model is running and no frame is judged at all. "
            "Nothing here is a real verdict."
        )
        frames = "Nothing is being captured or judged"
    elif is_local:
        lede = (
            "Frames are judged by a model running on this machine and dropped the moment a verdict "
            "exists. The verdicts are yours — export or delete them whenever."
        )
        frames = "Never written to disk, never sent anywhere"
    else:
        lede = (
            "Frames are sent to a hosted model to be judged, then dropped — nothing is written to "
            "disk. The verdicts are yours: export or delete them whenever."
        )
        frames = f"Never written to disk. Sent to {model} to be judged, then dropped"

    return {
        "lede": lede,
        "frames": frames,
        "database": f"{settings.db_path.name} — {counts['verdicts']} frame verdicts, "
        f"{counts['snapshots']} note snapshots, in your own folder",
        # Named explicitly rather than folded into "snapshots". Reading the work off
        # the screen is what makes the quizzes and progress work without configuring
        # anything, and it is also the most surprising thing the app keeps — so it
        # gets its own line, with its own count, and its own delete.
        "excerpts": (
            f"{counts['screen_excerpts']} short "
            f"{'excerpt' if counts['screen_excerpts'] == 1 else 'excerpts'} of your own writing, read "
            f"from frames already being judged and kept as text so questions come from your real work"
            if counts["screen_excerpts"]
            else "None kept yet — excerpts appear once a frame shows your own writing"
        ),
        "network": (
            "Open weights, no account, works offline"
            if is_local
            else "A hosted API is answering — this needs a connection"
        ),
        "network_badge": "none" if is_local else ("unused" if is_mock else "in use"),
        "local_inference": is_local,
        "mock": is_mock,
        "counts": counts,
        "recent_verdicts": _store.recent_verdicts(profile=profile, limit=3),
    }


@app.get("/api/export")
def api_export(profile: str = "default") -> Response:
    """Download everything held about this student as one JSON file."""
    payload = _store.export_all(profile=profile)
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="heid-doon-export.json"'},
    )


@app.post("/api/data/delete")
def api_delete_everything(profile: str = "default") -> dict[str, Any]:
    """Erase every session, verdict, snapshot and the learner model."""
    removed = _store.delete_all(profile=profile)
    # Drop in-memory sessions too, or a live one would keep writing to a store the
    # student just emptied.
    for session_id in list(_sessions):
        _sessions.pop(session_id, None)
        _streams.pop(session_id, None)
    return {"deleted": removed}


@app.get("/api/rules")
def api_rules(session_id: int | None = None, profile: str = "default") -> dict[str, Any]:
    """The whole rule base, as readable sentences with their weights.

    Exposed in full rather than summarised: a system that claims to be interpretable
    has to be willing to show all of its policy, including the rules that did not fire.
    """
    if session_id is not None:
        rules = _session(session_id).rules
    else:
        from .core.session import Session as _S  # local import keeps startup light

        rules = _S._load_rules(  # type: ignore[arg-type]
            type("_Stub", (), {"store": _store, "profile": profile})()
        )
    return {
        "rules": [rule.to_dict() for rule in rules],
        "percepts": [
            {
                "name": variable.name,
                "description": variable.description,
                "words": [fuzzy_set.name for fuzzy_set in variable.sets],
                "low_label": variable.low_label,
                "high_label": variable.high_label,
            }
            for variable in PERCEPTS.values()
        ],
        "decisions": [
            {
                "name": variable.name,
                "description": variable.description,
                "words": [fuzzy_set.name for fuzzy_set in variable.sets],
            }
            for variable in DECISIONS.values()
        ],
        "problems": validate(rules),
        "tuned": sum(1 for rule in rules if rule.tuned),
    }


@app.post("/api/session/{session_id}/rules/weight")
def api_set_weight(session_id: int, request: WeightRequest) -> dict[str, Any]:
    """Let the student retune a rule themselves. Autonomy applies to the rules too."""
    from .core.expert import MAX_WEIGHT, MIN_WEIGHT, PROTECTED

    session = _session(session_id)
    if not MIN_WEIGHT <= request.weight <= MAX_WEIGHT:
        raise HTTPException(status_code=400, detail=f"weight must be {MIN_WEIGHT}-{MAX_WEIGHT}")
    if request.rule_id in PROTECTED:
        raise HTTPException(
            status_code=403,
            detail="That rule is the product's ethical floor rather than a preference — "
            "it protects work in progress, silence when unsure, or not asking for what is "
            "already proven. It cannot be weakened.",
        )
    for rule in session.rules:
        if rule.id == request.rule_id:
            rule.history.append(f"{rule.weight:.2f} → {request.weight:.2f}: changed by the student")
            rule.weight = request.weight
            rule.tuned = True
            session.save_rules()
            return {"rule": rule.to_dict()}
    raise HTTPException(status_code=404, detail=f"no rule {request.rule_id!r}")


@app.post("/api/session/{session_id}/rules/reset")
def api_reset_weights(session_id: int, profile: str = "default") -> dict[str, Any]:
    """Back to the shipped defaults. A tunable system must be un-tunable too."""
    removed = _store.reset_rule_weights(profile=profile)
    session = _session(session_id)
    session.rules = session._load_rules()
    return {"reset": removed}


@app.get("/api/session/{session_id}/trace")
def api_trace(session_id: int) -> dict[str, Any]:
    """The last decision in full: degrees in, rules fired, outputs out."""
    session = _session(session_id)
    if session.last_trace is None:
        raise HTTPException(status_code=404, detail="no decision has been made in this session yet")
    return session.last_trace


@app.post("/api/session/{session_id}/expert-review")
async def api_expert_review(session_id: int) -> dict[str, Any]:
    """Have the expert agent tune this student's weights and profile their habits."""
    session = _session(session_id)
    result = await asyncio.to_thread(session.expert_review)
    return {"review": result.to_dict(), "rules": [rule.to_dict() for rule in session.rules]}


@app.get("/api/history")
def api_history(profile: str = "default") -> dict[str, Any]:
    """Past sessions and the learner model — the part that only exists across days."""
    sessions = _store.recent_sessions(profile=profile)
    for record in sessions:
        metadata = _store.get_study_metadata(record["id"])
        progress = _store.latest_progress(record["id"])
        record["study"] = metadata.to_dict() if metadata else None
        record["progress"] = progress.to_dict() if progress else None
    return {
        "sessions": sessions,
        "learner_model": _store.get_learner(profile=profile).to_dict(),
        "gamification": _store.get_gamification(profile=profile).to_dict(),
    }


@app.get("/api/progress/summary")
def api_progress_summary(profile: str = "default") -> dict[str, Any]:
    sessions = _store.recent_sessions(profile=profile, limit=100)
    points = []
    for record in reversed(sessions):
        progress = _store.latest_progress(record["id"])
        if progress is not None:
            points.append(
                {
                    "session_id": record["id"],
                    "started_at": record["started_at"],
                    "score": progress.score,
                    "new_concepts": progress.new_concepts,
                }
            )
    return {
        "points": points,
        "gamification": _store.get_gamification(profile=profile).to_dict(),
    }


@app.get("/api/personas")
def api_personas() -> dict[str, Any]:
    return {
        "personas": [
            {
                "id": persona.id,
                "label": persona.label,
                "tone": persona.tone,
                "tts_rate": persona.tts_rate,
                "tts_pitch": persona.tts_pitch,
            }
            for persona in list_personas()
        ]
    }


@app.on_event("shutdown")
async def _shutdown() -> None:
    """Never leave a capture loop running behind a dead server."""
    await _autopilot.stop_all()


# ── static UI ───────────────────────────────────────────────────────────────


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/app.js")
def app_js() -> FileResponse:
    return FileResponse(WEB_DIR / "app.js", media_type="text/javascript")


@app.get("/app.css")
def app_css() -> FileResponse:
    return FileResponse(WEB_DIR / "app.css", media_type="text/css")


@app.get("/angry-nudge.gif")
def angry_nudge_gif() -> FileResponse:
    return FileResponse(WEB_DIR / "angry-nudge.gif", media_type="image/gif")
