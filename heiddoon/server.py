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
import queue
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import prompts
from .config import settings
from .core.contract import compile_contract
from .core.session import Session
from .providers import Provider, ProviderError, get_provider
from .schemas import Contract, Event
from .store import SessionGone, Store

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="Heid Doon", version="0.1.0")

_store = Store(settings.db_path)
_sessions: dict[int, Session] = {}
_streams: dict[int, list[queue.SimpleQueue]] = {}


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


class DiffRequest(BaseModel):
    before: str
    after: str
    minutes: int = 20


class BreakRequest(BaseModel):
    notes: str | None = None


class AnswerRequest(BaseModel):
    answer: str


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


def _server_capture_available() -> bool:
    """Can this process see a screen? False on a headless or remote host."""
    try:
        from .watchers import screen as screen_mod

        return screen_mod.available()
    except Exception:  # noqa: BLE001
        return False


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
    session = Session(_provider(), contract, store=_store, profile=request.profile)
    _attach_stream(session)
    _sessions[session.id] = session
    return {
        "session_id": session.id,
        "contract": contract.to_dict(),
        "learner_model": session.learner.to_dict(),
    }


@app.get("/api/session/{session_id}")
def api_get_session(session_id: int) -> dict[str, Any]:
    session = _session(session_id)
    return {
        "session_id": session.id,
        "contract": session.contract.to_dict(),
        "elapsed_min": session.elapsed_min,
        "events": [event.to_dict() for event in session.events],
        "learner_model": session.learner.to_dict(),
    }


@app.post("/api/session/{session_id}/finish")
def api_finish(session_id: int) -> dict[str, Any]:
    session = _session(session_id)
    receipt = session.finish()
    _sessions.pop(session_id, None)
    return {"receipt": receipt.to_dict(), "repairs": receipt._repairs}


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

    verdict = await asyncio.to_thread(session.judge_frame, frame, kind=kind)
    return {"verdict": verdict.to_dict(), "repairs": verdict._repairs}


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

    verdict = await asyncio.to_thread(session.judge_frame, frame, kind="screen")
    return {"verdict": verdict.to_dict(), "repairs": verdict._repairs}


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
    quiz = await asyncio.to_thread(session.request_break, request.notes)
    if not quiz.question:
        raise HTTPException(status_code=502, detail="could not generate a question from those notes")
    # key_points are withheld: they are the answer, and this response goes to the
    # browser of the person being asked.
    return {"question": quiz.question, "n_key_points": len(quiz.key_points)}


@app.post("/api/session/{session_id}/break/answer")
async def api_break_answer(session_id: int, request: AnswerRequest) -> dict[str, Any]:
    session = _session(session_id)
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


@app.get("/api/history")
def api_history(profile: str = "default") -> dict[str, Any]:
    """Past sessions and the learner model — the part that only exists across days."""
    return {
        "sessions": _store.recent_sessions(profile=profile),
        "learner_model": _store.get_learner(profile=profile).to_dict(),
    }


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
