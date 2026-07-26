/* Heid Doon — front end.

   Holds no product logic. Every verdict, diff, grade and receipt comes from the
   server, which runs the same Session object the local watcher runs, so the UI
   cannot show something the event log does not contain. */

const state = {
  contract: null,
  sessionId: null,
  startedAt: null,
  events: [],
  stream: null,
  webcamStream: null,
  signals: { screen: true, camera: true, diff: true, idle: false },
  tone: "warm",
  breakTimer: null,
  breakEndsAt: null,
  breakTotal: 0,
  serverCapture: false,
  autopilot: false,
  autoCadence: 60,
  pageCamStream: null,
  manualBusy: false,
};

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};
const icon = (name, cls = "ic") => {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", cls);
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#${name}`);
  svg.appendChild(use);
  return svg;
};
const clockOf = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

function snack(message, isError = false) {
  const node = el("div", `snackbar${isError ? " err" : ""}`);
  node.appendChild(icon(isError ? "i-alert" : "i-check", "ic sm"));
  node.appendChild(el("span", null, message));
  document.body.appendChild(node);
  setTimeout(() => node.remove(), isError ? 7000 : 3500);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    let body = {};
    try {
      body = await response.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* non-JSON error body */ }
    // The session went away underneath us — reset rather than leaving the UI
    // pointing at an id the server will keep rejecting.
    if (response.status === 409 && body.session_gone) forgetSession();
    throw new Error(detail);
  }
  return response.json();
}

/* Drop every trace of the current session from the UI. Used when the session ends,
   when its data is deleted, and when the server tells us it has vanished. */
function forgetSession() {
  state.sessionId = null;
  state.startedAt = null;
  state.events = [];
  if (state.stream) { state.stream.close(); state.stream = null; }
  stopAllCameras();
  $("nav-watch").disabled = true;
  $("nav-receipt").disabled = true;
  $("feed").innerHTML = '<div class="feed-empty">Nothing yet.</div>';
  $("verdict-count").textContent = "";
  $("status-text").textContent = "idle";
  state.autopilot = false;
  $("auto-toggle").classList.remove("on");
  hidePageAsk();
}

/* Long model calls are the normal case here, not the exception — a vision call
   takes many seconds. So anything that waits says so, and blocks a second click
   rather than firing an identical request. */
function withBusy(button, label) {
  const original = button ? button.textContent : null;
  state.manualBusy = true;
  $("status-chip").classList.add("busy");
  $("status-text").textContent = label;
  if (button) { button.disabled = true; button.dataset.wasText = original; button.textContent = "Working…"; }
  return () => {
    state.manualBusy = false;
    $("status-chip").classList.remove("busy");
    $("status-text").textContent = state.sessionId ? "watching" : "idle";
    if (button) { button.disabled = false; button.textContent = button.dataset.wasText || original; }
  };
}

/* ── navigation ─────────────────────────────────────────────────────────── */

const TITLES = {
  contract: "New session",
  watch: "Watching",
  receipt: "Receipt",
  history: "History",
  privacy: "Privacy",
};

function show(name) {
  if (!TITLES[name]) name = "contract";
  document.querySelectorAll(".screen").forEach((node) => node.classList.remove("active"));
  $(`scr-${name}`).classList.add("active");
  document.querySelectorAll(".rail-btn").forEach((node) =>
    node.classList.toggle("active", node.dataset.screen === name));
  $("bar-title").textContent = TITLES[name];
  // Reflect the screen in the URL so a screen can be linked or bookmarked — and
  // so a demo can open straight onto the one it needs.
  if (window.location.hash.slice(1) !== name) window.history.replaceState(null, "", `#${name}`);
  if (name !== "watch") stopAllCameras();
  if (name === "history") loadHistory();
  if (name === "privacy") loadPrivacy();
}
document.querySelectorAll(".rail-btn").forEach((node) =>
  node.addEventListener("click", () => show(node.dataset.screen)));
window.addEventListener("hashchange", () => show(window.location.hash.slice(1)));

/* ── status: the header must describe the real configuration ────────────── */

async function loadStatus() {
  try {
    const status = await api("/api/status");
    const badge = $("model-badge");
    badge.textContent = status.provider_ready ? status.provider : "model unavailable";
    badge.classList.toggle("down", !status.provider_ready);
    badge.classList.toggle("mock", !!status.mock);
    if (status.mock) badge.textContent = "MOCK — no model running";
    $("bar-note").textContent = status.local_inference ? "on this machine" : "hosted";
    $("sig-screen-desc").textContent = `Judged every ${status.cadence_s} seconds`;
    // Say which screen the button is about to read — the server's, or whichever
    // window the browser picker offers.
    state.serverCapture = !!status.server_capture;
    let saved = null;
    try { saved = Number(localStorage.getItem("heiddoon.cadence")) || null; } catch { /* private mode */ }
    state.autoCadence = saved || status.auto_cadence_s || 60;
    paintPace();
    $("capture-hint").textContent = state.serverCapture
      ? "Grabs this machine's screen as it is right now, judges it, and drops it. No dialog, nothing stored."
      : "Asks which window or screen to share, grabs one frame, and stops. Nothing keeps watching.";
    if (!status.provider_ready) snack(status.provider, true);
  } catch {
    $("model-badge").textContent = "server unreachable";
    $("model-badge").classList.add("down");
  }
}

/* ── contract (3a) ──────────────────────────────────────────────────────── */

const EXAMPLE = `Two hours on thermodynamics chapter 4 — entropy. Lecture videos and PDFs about thermodynamics are fine, music is fine, and my study group chat is fine when we're actually discussing the problem set. No social media, no entertainment videos. I'm writing into notes_thermo.md. This is the chapter I keep dodging and the exam is Thursday.`;

$("btn-example").addEventListener("click", () => {
  $("contract-text").value = EXAMPLE;
  updateCount();
});

function updateCount() {
  const field = $("contract-text");
  $("char-count").textContent = `${field.value.length}/${field.maxLength}`;
}
$("contract-text").addEventListener("input", updateCount);
updateCount();

$("signals").addEventListener("click", (event) => {
  const button = event.target.closest(".signal");
  if (!button) return;
  const name = button.dataset.signal;
  state.signals[name] = !state.signals[name];
  button.classList.toggle("on", state.signals[name]);
});

$("c-tone").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-tone]");
  if (!button) return;
  state.tone = button.dataset.tone;
  paintTone();
});
function paintTone() {
  document.querySelectorAll("#c-tone button").forEach((node) =>
    node.classList.toggle("on", node.dataset.tone === state.tone));
}

$("btn-compile").addEventListener("click", async (event) => {
  const text = $("contract-text").value.trim();
  if (!text) { snack("Write your rules first.", true); return; }
  const done = withBusy(event.target, "compiling");
  try {
    const { contract, repairs } = await api("/api/contract/compile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    state.contract = contract;
    renderCompiled(contract);
    if (repairs && repairs.length) snack(`Compiled, with ${repairs.length} field(s) repaired.`);
  } catch (error) {
    snack(`Could not compile: ${error.message}`, true);
  } finally { done(); }
});

function renderCompiled(contract) {
  $("compiled-empty").classList.add("hidden");
  $("compiled-body").classList.remove("hidden");
  $("btn-start").classList.remove("hidden");
  $("compiled-state").textContent = "editable";

  $("c-task").textContent = contract.task || "—";
  $("c-why").textContent = contract.why ? `“${contract.why}”` : "— (nudges will be plainer without one)";
  $("c-artifacts").textContent = (contract.artifacts || []).join(", ") || "none named";
  $("c-ends").textContent = contract.ends || "when you say so";

  const fill = (id, items, cls) => {
    const host = $(id);
    host.innerHTML = "";
    if (!items || !items.length) { host.appendChild(el("span", "chip neutral", "none")); return; }
    items.forEach((item) => host.appendChild(el("span", `chip ${cls}`, item)));
  };
  fill("c-allowed", contract.allowed, "allow");
  fill("c-blocked", contract.blocked, "block");

  // The compiler reads a tone out of the student's own words; reflect it in the
  // segmented control rather than overriding what they wrote.
  const tone = (contract.tone || "").toLowerCase();
  state.tone = tone.includes("blunt") || tone.includes("sharp") ? "blunt"
    : tone.includes("plain") || tone.includes("dry") ? "plain" : "warm";
  paintTone();

  // Signals the contract asked for win over the toggles' defaults.
  if (contract.signals && contract.signals.length) {
    Object.keys(state.signals).forEach((name) => { state.signals[name] = contract.signals.includes(name); });
    document.querySelectorAll(".signal").forEach((node) =>
      node.classList.toggle("on", !!state.signals[node.dataset.signal]));
  }
  if (contract.artifacts && contract.artifacts.length) {
    $("sig-diff-desc").textContent = `${contract.artifacts.join(", ")} · read for progress, not content`;
  }
}

$("btn-start").addEventListener("click", async (event) => {
  const done = withBusy(event.target, "starting");
  try {
    const contract = {
      ...state.contract,
      signals: Object.keys(state.signals).filter((name) => state.signals[name]),
      tone: state.tone,
    };
    const data = await api("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contract }),
    });
    state.sessionId = data.session_id;
    state.startedAt = Date.now();
    state.events = [];
    $("nav-watch").disabled = false;
    $("nav-receipt").disabled = false;
    renderArtifactButton(data.contract.artifacts || []);
    subscribe(data.session_id);
    startClock();
    show("watch");
    $("status-text").textContent = "watching";
    // On by default. Being watched should not require a second decision after
    // the one the student already made by starting a session.
    state.autopilot = true;
    await setAutopilot(true, { quiet: true });
  } catch (error) {
    snack(`Could not start: ${error.message}`, true);
  } finally { done(); }
});

/* ── the clock ring ─────────────────────────────────────────────────────── */

function startClock() {
  const tick = () => {
    if (!state.startedAt) return;
    const seconds = Math.floor((Date.now() - state.startedAt) / 1000);
    $("clock").textContent = clockOf(seconds);
    // A 50-minute session fills the ring; beyond that it simply stays full.
    const fraction = Math.min(1, seconds / (50 * 60));
    $("ring-fg").setAttribute("stroke-dashoffset", String(503 * (1 - fraction)));
  };
  tick();
  setInterval(tick, 1000);
}

/* ── live feed ──────────────────────────────────────────────────────────── */

function subscribe(sessionId) {
  if (state.stream) state.stream.close();
  state.stream = new EventSource(`/api/session/${sessionId}/stream`);
  state.stream.onmessage = (message) => {
    const event = JSON.parse(message.data);
    state.events.push(event);
    addFeedRow(event);
    $("verdict-count").textContent = `${state.events.length} recorded`;
  };
}

function addFeedRow(event) {
  // A request for a page is not something that happened to the student's focus,
  // so it belongs in the card, not in the verdict log.
  if (event.kind === "ask_notes") return;
  const feed = $("feed");
  feed.querySelector(".feed-empty")?.remove();

  const detail = event.detail || {};
  let kind = "work";
  let name = "i-doc";
  if (event.on_task === true) { kind = "ok"; name = "i-check"; }
  else if (event.on_task === false) { kind = "bad"; name = event.kind === "camera" ? "i-camera" : "i-alert"; }

  const row = el("div", `verdict ${kind}`);
  const wrap = el("span", "ic-wrap");
  wrap.appendChild(icon(name, "ic sm"));
  row.appendChild(wrap);

  const txt = el("span", "txt");
  if (event.kind === "diff") {
    const delta = detail.delta_words >= 0 ? `+${detail.delta_words}` : `${detail.delta_words}`;
    txt.appendChild(el("span", "what", `${event.seen} — ${detail.verdict} (${delta} words)`));
    txt.appendChild(el("span", "why", detail.quality_note || detail.summary || ""));
  } else if (event.kind === "quiz") {
    txt.appendChild(el("span", "what", detail.pass ? "Break earned" : "Break not earned"));
    txt.appendChild(el("span", "why", detail.feedback || ""));
  } else {
    txt.appendChild(el("span", "what", event.seen || event.kind));
    txt.appendChild(el("span", "why", detail.nudge || detail.reason || ""));
  }
  row.appendChild(txt);

  const meta = el("span", "meta");
  meta.appendChild(el("span", null, new Date(event.at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })));
  if (detail.latency_s) meta.appendChild(el("div", "lat", `${detail.latency_s}s`));
  if (detail.confidence === "low") meta.appendChild(el("div", "lat", "low conf."));
  row.appendChild(meta);

  feed.prepend(row);

  if (event.kind === "ask_notes") { showPageAsk(detail.prompt); return; }
  if (event.on_task === false && (detail.nudge || "").length) showNudge(detail.nudge, event.seen);
}

/* ── frames ─────────────────────────────────────────────────────────────── */

async function judgeBlob(blob, kind, button) {
  if (!state.sessionId) { snack("Start a session first.", true); return; }
  const done = withBusy(button, kind === "camera" ? "reading the room" : "reading the screen");
  try {
    const form = new FormData();
    form.append("file", blob, "frame.png");
    await api(`/api/session/${state.sessionId}/frame?kind=${kind}`, { method: "POST", body: form });
  } catch (error) {
    snack(`Could not judge that frame: ${error.message}`, true);
  } finally { done(); }
}

$("dropzone").addEventListener("click", () => $("frame-file").click());
$("frame-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (file) judgeBlob(file, "screen", null);
  event.target.value = "";
});
["dragover", "dragleave", "drop"].forEach((name) =>
  $("dropzone").addEventListener(name, (event) => {
    event.preventDefault();
    $("dropzone").classList.toggle("hot", name === "dragover");
    if (name === "drop" && event.dataTransfer.files[0]) judgeBlob(event.dataTransfer.files[0], "screen", null);
  }));

/* Grab a still from a live MediaStream. Shared by the screen and webcam paths:
   both need a frame from a stream, and neither should hold the device open once
   it has one. */
async function grabStill(stream) {
  const video = document.createElement("video");
  video.srcObject = stream;
  video.muted = true;
  await video.play();
  // Wait for real pixels — a video that has started can still report 0×0 for a
  // frame or two, and a zero-size canvas produces a blank image the model would
  // dutifully describe as an empty screen.
  for (let attempt = 0; attempt < 40 && !video.videoWidth; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  if (!video.videoWidth) throw new Error("the stream produced no frames");

  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  video.pause();
  video.srcObject = null;
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
}

/* Capture the screen and judge it.

   Two routes, because the browser one is not always available:

   1. Server-side, via mss — the same code the local watcher uses. Preferred when
      the server reports it can see a display: one click, whole screen, no dialog,
      and it works in embedded webviews where getDisplayMedia throws
      NotSupportedError.
   2. The browser's getDisplayMedia, as a fallback for when the server is headless
      or running on a different machine from the student.

   Either way the frame exists only for the length of one call. */
$("btn-screenshot").addEventListener("click", async (event) => {
  if (!state.sessionId) { snack("Start a session first.", true); return; }
  const done = withBusy(event.target, "reading your screen");
  try {
    if (state.serverCapture) {
      await api(`/api/session/${state.sessionId}/capture-screen`, { method: "POST" });
      return;
    }
    await captureViaBrowser();
  } catch (error) {
    snack(`Could not capture: ${error.message}`, true);
  } finally { done(); }
});

async function captureViaBrowser() {
  if (!navigator.mediaDevices?.getDisplayMedia) {
    throw new Error("this browser cannot capture the screen — drop an image instead");
  }
  let stream;
  try {
    // No `displaySurface` hint: some browsers reject unknown video constraints
    // outright with NotSupportedError rather than ignoring them.
    stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
  } catch (error) {
    // Dismissing the picker is a normal choice, not an error worth shouting about.
    if (error.name === "NotAllowedError") return;
    if (error.name === "NotSupportedError") {
      throw new Error("this browser refuses screen capture — try Chrome or Firefox directly, "
        + "or install mss on the server so it can grab the screen itself");
    }
    throw error;
  }
  try {
    const blob = await grabStill(stream);
    const form = new FormData();
    form.append("file", blob, "screen.jpg");
    await api(`/api/session/${state.sessionId}/frame?kind=screen`, { method: "POST", body: form });
  } finally {
    // Stop immediately, so the browser's sharing indicator goes off: this is one
    // glance, not a session of watching.
    stream.getTracks().forEach((track) => track.stop());
  }
}

$("btn-webcam").addEventListener("click", async () => {
  try {
    state.webcamStream = await navigator.mediaDevices.getUserMedia({ video: true });
    $("webcam").srcObject = state.webcamStream;
    $("webcam").classList.remove("hidden");
    $("btn-snap").classList.remove("hidden");
    $("btn-snap").disabled = false;
  } catch (error) {
    snack(`No camera: ${error.message}`, true);
  }
});

$("btn-snap").addEventListener("click", async (event) => {
  if (!state.webcamStream) { snack("Turn the webcam on first.", true); return; }
  try {
    await judgeBlob(await grabStill(state.webcamStream), "camera", event.target);
  } catch (error) {
    snack(`Could not take that frame: ${error.message}`, true);
  } finally {
    // One glance, then the light goes out. A preview left running is a camera the
    // student has to keep trusting, and the whole point is that it looks once.
    stopWebcam();
  }
});

function stopWebcam() {
  if (state.webcamStream) {
    state.webcamStream.getTracks().forEach((track) => track.stop());
    state.webcamStream = null;
  }
  $("webcam").srcObject = null;
  $("webcam").classList.add("hidden");
  $("btn-snap").classList.add("hidden");
}

/* Any camera, anywhere, off. Used when a photo is done with, when the session ends,
   and when the student navigates away from the watch screen. */
function stopAllCameras() {
  stopWebcam();
  stopPageCam();
}

/* ── autopilot: watching without being asked to ─────────────────────────── */

async function setAutopilot(enabled, { quiet = false } = {}) {
  if (!state.sessionId) return;
  try {
    const { autopilot } = await api(`/api/session/${state.sessionId}/autopilot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, cadence_s: state.autoCadence }),
    });
    state.autopilot = enabled && autopilot.running;
    paintAutopilot(autopilot);
  } catch (error) {
    state.autopilot = false;
    $("auto-toggle").classList.remove("on");
    $("auto-desc").textContent = "Not available — check frames yourself below";
    if (!quiet) snack(error.message, true);
  }
}

function paintAutopilot(autopilot) {
  $("auto-toggle").classList.toggle("on", state.autopilot);
  $("auto-desc").textContent = state.autopilot
    ? `Checking the screen every ${state.autoCadence}s on its own`
    : "Paused — nothing is being looked at";
  if (autopilot && (autopilot.checks || autopilot.skipped_unchanged)) {
    $("auto-stats").textContent =
      `${autopilot.checks} judged · ${autopilot.skipped_unchanged} skipped as unchanged`;
  }
}

$("auto-toggle").addEventListener("click", () => setAutopilot(!state.autopilot));

/* Pace. A demo runs in two minutes, not two hours, so the cadence has to be
   changeable on stage without editing a file and restarting. Kept in localStorage
   so a reload mid-demo does not quietly drop back to the slow setting. */
const PACE_NOTES = {
  60: "Every 60 seconds. The everyday setting — cheap, and quick enough to catch drift.",
  20: "Every 20 seconds, matching the local watcher.",
  5: "As fast as it can manage. A vision call takes 13–15s, so checks run back to back "
    + "rather than literally every 5s. For demos, not for studying.",
};

function paintPace() {
  document.querySelectorAll("#pace button").forEach((node) =>
    node.classList.toggle("on", Number(node.dataset.cadence) === state.autoCadence));
  $("pace-note").textContent = PACE_NOTES[state.autoCadence] || "";
}

$("pace").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-cadence]");
  if (!button) return;
  state.autoCadence = Number(button.dataset.cadence);
  try { localStorage.setItem("heiddoon.cadence", String(state.autoCadence)); } catch { /* private mode */ }
  paintPace();
  if (state.sessionId && state.autopilot) {
    // Restart the loop so the new pace takes effect now rather than after the
    // current sleep, which at 60s would be a long wait in front of an audience.
    await setAutopilot(false, { quiet: true });
    await setAutopilot(true);
  }
});

/* Poll the loop often enough to feel live. The verdicts themselves arrive over the
   event stream; this drives the "is it alive, is it thinking" line.

   Two seconds, not fifteen: a verdict takes about sixteen seconds and cannot be
   hurried, so the only thing that makes the wait bearable is showing that it is
   happening. It is a local request against our own process — the cost is nil. */
setInterval(async () => {
  if (!state.sessionId || !state.autopilot) return;
  try {
    const { autopilot } = await api(`/api/session/${state.sessionId}/autopilot`);
    state.autopilot = autopilot.running;
    paintAutopilot(autopilot);
    // Do not fight a manual action for the status chip — that has its own label.
    if (!state.manualBusy) {
      $("status-chip").classList.toggle("busy", !!autopilot.busy);
      $("status-text").textContent = autopilot.busy ? "reading your screen" : "watching";
    }
    if (autopilot.last_error) $("auto-desc").textContent = autopilot.last_error;
  } catch { /* a hiccup here is not worth a message */ }
}, 2000);

/* ── the page request ───────────────────────────────────────────────────── */

function showPageAsk(line) {
  if (line) $("page-ask-line").textContent = line;
  $("page-ask").classList.remove("hidden");
}

function hidePageAsk() {
  $("page-ask").classList.add("hidden");
  stopPageCam();
}

/* "Not now" is a real answer. It closes the card and does not count against
   anything — the next ask is on the normal interval, and nothing is logged. */
$("btn-page-later").addEventListener("click", hidePageAsk);

function stopPageCam() {
  if (state.pageCamStream) {
    state.pageCamStream.getTracks().forEach((track) => track.stop());
    state.pageCamStream = null;
  }
  $("page-cam").classList.add("hidden");
  $("page-shoot-actions").classList.add("hidden");
}

$("btn-page-camera").addEventListener("click", async () => {
  try {
    // Prefer the rear camera on a phone: this is a photo of a notebook on a desk,
    // not a selfie.
    state.pageCamStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
    });
    $("page-cam").srcObject = state.pageCamStream;
    $("page-cam").classList.remove("hidden");
    $("page-shoot-actions").classList.remove("hidden");
  } catch (error) {
    snack(`No camera: ${error.message} — upload a photo instead`, true);
  }
});

$("btn-page-cancel").addEventListener("click", stopPageCam);
$("btn-page-upload").addEventListener("click", () => $("page-file").click());
$("page-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (file) readPage(file, null);
  event.target.value = "";
});

$("btn-page-shoot").addEventListener("click", async (event) => {
  if (!state.pageCamStream) return;
  try {
    const still = await grabStill(state.pageCamStream);
    // Close the camera before the model call, not after: the photo is already
    // taken, and leaving a preview up for fifteen seconds of reading looks like
    // it is still watching.
    stopPageCam();
    await readPage(still, event.target);
  } catch (error) {
    stopPageCam();
    snack(`Could not take that photo: ${error.message}`, true);
  }
});

async function readPage(blob, button) {
  const done = withBusy(button, "reading your page");
  try {
    const form = new FormData();
    form.append("file", blob, "page.jpg");
    const result = await api(`/api/session/${state.sessionId}/notes-photo`, {
      method: "POST",
      body: form,
    });
    if (!result.ok) {
      // A bad photo is not a failure on their part, and not an event either.
      snack(result.problem, true);
      return;
    }
    hidePageAsk();
    if (result.baseline) {
      snack(`Got it — ${result.page_note || "page read"}. I will compare the next one against this.`);
    } else if (result.diff) {
      snack(`${result.diff.verdict} — ${result.diff.summary}`);
    }
  } catch (error) {
    snack(`Could not read that page: ${error.message}`, true);
  } finally { done(); }
}

/* ── work-diff ──────────────────────────────────────────────────────────── */

function renderArtifactButton(artifacts) {
  const host = $("artifact-actions");
  host.innerHTML = "";
  if (!artifacts.length) {
    host.appendChild(el("span", "hint", "This contract names no file — paste two versions below instead."));
    return;
  }
  const button = el("button", "btn btn-tonal sm", `Check ${artifacts.join(", ")} on disk`);
  button.addEventListener("click", async () => {
    const done = withBusy(button, "reading your file");
    try {
      const { diffs } = await api(`/api/session/${state.sessionId}/artifact-check`, { method: "POST" });
      const baselined = Object.entries(diffs).filter(([, value]) => value === null).map(([key]) => key);
      if (baselined.length) snack(`Baseline recorded for ${baselined.join(", ")} — check again after writing.`);
    } catch (error) {
      snack(`Could not check the file: ${error.message}`, true);
    } finally { done(); }
  });
  host.appendChild(button);
}

$("btn-diff").addEventListener("click", async (event) => {
  const before = $("diff-before").value;
  const after = $("diff-after").value;
  if (!before.trim() && !after.trim()) { snack("Paste two versions of your page.", true); return; }
  const done = withBusy(event.target, "reading your work");
  try {
    await api(`/api/session/${state.sessionId}/diff`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ before, after, minutes: 20 }),
    });
  } catch (error) {
    snack(`Could not judge that delta: ${error.message}`, true);
  } finally { done(); }
});

/* ── nudge, bouncer, break (3b) ─────────────────────────────────────────── */

async function playNudgeSpeech(text) {
  try {
    const response = await fetch("/api/tss", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: "en-us" }),
    });
    if (!response.ok) throw new Error("speech unavailable");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.play().catch(() => {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      window.speechSynthesis.speak(utterance);
    });
  } catch {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    window.speechSynthesis.speak(utterance);
  }
}

function showNudge(line, seen) {
  $("nudge-line").textContent = line;
  $("nudge-seen").textContent = seen ? `Seen: ${seen}` : "";
  $("ov-nudge").classList.add("open");
  void playNudgeSpeech(line);
}
$("btn-backtoit").addEventListener("click", () => $("ov-nudge").classList.remove("open"));
$("btn-open-bouncer").addEventListener("click", () => {
  $("ov-nudge").classList.remove("open");
  askForBreak();
});
$("btn-break").addEventListener("click", askForBreak);
$("btn-close-bouncer").addEventListener("click", () => $("ov-bouncer").classList.remove("open"));

async function askForBreak() {
  if (!state.sessionId) { snack("Start a session first.", true); return; }
  $("bouncer-question").textContent = "Thinking of something to ask you…";
  $("bouncer-source").textContent = "";
  $("bouncer-result").classList.add("hidden");
  $("bouncer-answer").value = "";
  $("ov-bouncer").classList.add("open");
  try {
    const notes = $("diff-after").value.trim() || null;
    const { question, source } = await api(`/api/session/${state.sessionId}/break`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes }),
    });
    $("bouncer-question").textContent = question;
    $("bouncer-source").textContent = `from ${source || "your own notes"}`;
  } catch (error) {
    $("bouncer-question").textContent = "Could not think of a question just now.";
    snack(error.message, true);
  }
}

$("btn-answer").addEventListener("click", async (event) => {
  const done = withBusy(event.target, "marking");
  try {
    const grade = await api(`/api/session/${state.sessionId}/break/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer: $("bouncer-answer").value }),
    });
    const box = $("bouncer-result");
    box.className = `result ${grade.pass ? "pass" : "fail"}`;
    $("bouncer-result-title").textContent = grade.pass ? "Passed — off you go" : "Not quite yet";
    $("bouncer-result-detail").textContent = grade.feedback || "";
    if (grade.pass) setTimeout(() => { $("ov-bouncer").classList.remove("open"); startBreak(10); }, 1600);
  } catch (error) {
    snack(error.message, true);
  } finally { done(); }
});

function startBreak(minutes) {
  setBreakState(true);
  state.breakTotal = minutes;
  state.breakEndsAt = Date.now() + minutes * 60000;
  $("break-of").textContent = `of ${minutes} minutes`;
  $("ov-break").classList.add("open");
  const back = new Date(state.breakEndsAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  $("break-line").textContent = `Go and look out a window. I'll come and get you at ${back}.`;
  clearInterval(state.breakTimer);
  state.breakTimer = setInterval(tickBreak, 250);
  tickBreak();
}

function tickBreak() {
  const remaining = Math.max(0, state.breakEndsAt - Date.now()) / 1000;
  $("break-clock").textContent = clockOf(remaining);
  $("break-track").style.width = `${(remaining / (state.breakTotal * 60)) * 100}%`;
  if (remaining <= 0) endBreak();
}

function endBreak() {
  clearInterval(state.breakTimer);
  state.breakTimer = null;
  $("ov-break").classList.remove("open");
  setBreakState(false);
}

/* An earned break should be undisturbed, so the session stops asking for anything
   until it is over. */
async function setBreakState(onBreak) {
  if (!state.sessionId) return;
  try {
    await api(`/api/session/${state.sessionId}/break-state`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on_break: onBreak }),
    });
  } catch { /* the break still works if this does not land */ }
}
$("btn-break-back").addEventListener("click", endBreak);
$("btn-break-add").addEventListener("click", () => {
  state.breakEndsAt += 3 * 60000;
  state.breakTotal += 3;
  $("break-of").textContent = `of ${state.breakTotal} minutes`;
});

/* ── receipt (3c) ───────────────────────────────────────────────────────── */

$("btn-finish").addEventListener("click", async (event) => {
  if (!state.sessionId) { snack("No session running.", true); return; }
  const done = withBusy(event.target, "writing your receipt");
  try {
    const { receipt } = await api(`/api/session/${state.sessionId}/finish`, { method: "POST" });
    renderReceipt(receipt);
    // The server stops the watch loop on finish; this is the browser's half —
    // close the event stream and every camera before showing the receipt.
    if (state.stream) { state.stream.close(); state.stream = null; }
    stopAllCameras();
    state.autopilot = false;
    $("auto-toggle").classList.remove("on");
    hidePageAsk();
    show("receipt");
  } catch (error) {
    snack(`Could not finish: ${error.message}`, true);
  } finally { done(); }
});

function renderReceipt(receipt) {
  const checks = state.events.filter((event) => event.kind === "screen" || event.kind === "camera");
  const drifted = checks.filter((event) => event.on_task === false);
  const diffs = state.events.filter((event) => event.kind === "diff");
  const words = diffs.reduce((total, event) => total + (event.detail.delta_words || 0), 0);
  const minutes = Math.floor((Date.now() - state.startedAt) / 60000);

  $("r-score").textContent = receipt.focus_score;
  $("r-delta").textContent = words > 0 ? `+${words} words` : "";
  $("r-autopsy").textContent = receipt.autopsy;
  $("r-tomorrow").textContent = receipt.tomorrow || "—";

  const started = new Date(state.startedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const ended = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  $("r-span").textContent = `${started} → ${ended} · ${minutes} min · no frames stored`;
  $("lg-on").textContent = `on task ${checks.length - drifted.length}`;
  $("lg-drift").textContent = `drift ${drifted.length}`;
  $("lg-work").textContent = `work checked ${diffs.length}`;

  // The session bar. Each event is a segment; drift and idle are hatched rather
  // than coloured, per the design — a gap reads as absence, not as a red mark.
  const timeline = $("r-timeline");
  timeline.innerHTML = "";
  if (!state.events.length) {
    timeline.appendChild(el("div", "seg drift", ""));
  } else {
    state.events.forEach((event) => {
      const segment = el("span", "seg");
      segment.style.flex = "1";
      if (event.kind === "diff") segment.classList.add("work");
      else if (event.kind === "idle") segment.classList.add("idle");
      else if (event.on_task === false) segment.classList.add("drift");
      segment.title = `${event.kind}: ${event.seen || ""}`;
      timeline.appendChild(segment);
    });
  }

  // Drift autopsy: the actual drift events, then the model's pattern read.
  const list = $("r-drift-list");
  list.innerHTML = "";
  if (!drifted.length) {
    const row = el("div", "ev");
    row.appendChild(el("span", "t", "—"));
    row.appendChild(el("span", "pip"));
    const txt = el("div");
    txt.appendChild(el("div", "what", "No drift recorded this session."));
    txt.appendChild(el("div", "why", "Whatever you did to set this one up, do it again."));
    row.appendChild(txt);
    list.appendChild(row);
  } else {
    drifted.forEach((event) => {
      const row = el("div", "ev");
      row.appendChild(el("span", "t", new Date(event.at * 1000)
        .toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })));
      row.appendChild(el("span", "pip"));
      const txt = el("div");
      txt.style.flex = "1";
      txt.appendChild(el("div", "what", event.seen || "drift"));
      txt.appendChild(el("div", "why", (event.detail || {}).nudge || (event.detail || {}).reason || ""));
      row.appendChild(txt);
      list.appendChild(row);
    });
  }
  const insight = el("div", "insight");
  insight.appendChild(icon("i-insights", "ic"));
  insight.appendChild(el("div", "txt", receipt.autopsy || "Too short a log to read a pattern yet."));
  list.appendChild(insight);

  renderLearner("r-learner", receipt.learner_model);
  loadStreak();
}

function renderLearner(hostId, learner) {
  const host = $(hostId);
  host.innerHTML = "";
  const rows = [
    ["weak", (learner.weak_topics || []).join(", ")],
    ["strong", (learner.strong_topics || []).join(", ")],
    ["drift trigger", (learner.drift_patterns || []).join(" · ")],
    ["focus streak", learner.avg_focus_streak_min ? `${learner.avg_focus_streak_min} min avg` : ""],
    ["best nudge", learner.best_nudge_style || ""],
    ["next", learner.next_difficulty || ""],
  ];
  rows.forEach(([key, value]) => {
    const row = el("div");
    row.appendChild(el("span", "k", `${key} `));
    row.appendChild(document.createTextNode(value || "not yet known"));
    host.appendChild(row);
  });
}

/* The streak squares are drawn from real sessions, not decoration: a missed day
   is hatched rather than absent, because the design makes the point that the
   streak survives a lapse. */
async function loadStreak() {
  try {
    const { sessions } = await api("/api/history");
    const days = new Set(sessions.map((s) => new Date(s.started_at * 1000).toDateString()));
    const host = $("r-streak");
    host.innerHTML = "";
    let active = 0;
    for (let back = 5; back >= 0; back -= 1) {
      const day = new Date(Date.now() - back * 86400000).toDateString();
      const hit = days.has(day);
      if (hit) active += 1;
      host.appendChild(el("span", `day${hit ? "" : " miss"}`));
    }
    $("r-streak-label").textContent = `Sessions · ${sessions.length} total`;
    $("r-streak-note").textContent = active >= 6
      ? "Six days running. Whatever you are doing, keep doing it."
      : "Hatched days are ones you missed — the streak carries on regardless. A lapse is not a relapse.";
  } catch { /* the receipt is still valid without the streak */ }
}

$("btn-accept-tomorrow").addEventListener("click", () => {
  $("contract-text").value = $("r-tomorrow").textContent;
  updateCount();
  snack("Drafted into a new contract — edit it, then compile.");
  show("contract");
});
$("btn-edit-rules").addEventListener("click", () => show("contract"));

/* ── history ────────────────────────────────────────────────────────────── */

async function loadHistory() {
  try {
    const data = await api("/api/history");
    const host = $("h-sessions");
    host.innerHTML = "";
    if (!data.sessions.length) {
      host.appendChild(el("div", "feed-empty", "No sessions recorded yet."));
    }
    data.sessions.forEach((session) => {
      const row = el("div", "session-row");
      const pip = el("span", `score-pip${session.ended_at ? "" : " open"}`,
        session.focus_score ?? "–");
      row.appendChild(pip);
      const txt = el("span", "txt");
      txt.style.flex = "1";
      txt.appendChild(el("div", "name", `Session ${session.id}`));
      txt.appendChild(el("div", "desc", session.ended_at ? "finished" : "still open"));
      row.appendChild(txt);
      row.appendChild(el("span", "meta mono",
        new Date(session.started_at * 1000).toLocaleString([], {
          day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
        })));
      host.appendChild(row);
    });
    renderLearner("h-learner", data.learner_model);
  } catch (error) {
    snack(error.message, true);
  }
}

/* ── privacy (3d) ───────────────────────────────────────────────────────── */

async function loadPrivacy() {
  try {
    const data = await api("/api/privacy");
    $("privacy-lede").textContent = data.lede;
    $("privacy-frames").textContent = data.frames;
    $("privacy-db").textContent = data.database;
    $("privacy-network").textContent = data.network;
    const badge = $("privacy-network-badge");
    badge.textContent = data.network_badge;
    badge.className = `badge ${data.local_inference ? "none" : "inuse"}`;

    const log = $("privacy-log");
    log.innerHTML = "";
    if (!data.recent_verdicts.length) {
      log.appendChild(el("span", "log-empty", "No verdicts recorded yet."));
    }
    data.recent_verdicts.forEach((verdict) => {
      const row = el("div");
      const when = new Date(verdict.at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      row.appendChild(el("span", verdict.on_task ? "on" : "off",
        `${when} ${verdict.on_task ? "on_task" : "off_task"}`));
      row.appendChild(document.createTextNode(` · ${verdict.seen}`));
      log.appendChild(row);
    });
  } catch (error) {
    snack(error.message, true);
  }
}

$("btn-export").addEventListener("click", () => {
  // A plain navigation, so the browser's own download UI handles it.
  window.location.href = "/api/export";
});

$("btn-delete").addEventListener("click", async (event) => {
  const { counts } = await api("/api/privacy").catch(() => ({ counts: null }));
  const summary = counts
    ? `${counts.sessions} sessions, ${counts.events} verdicts and ${counts.snapshots} note snapshots`
    : "everything";
  if (!window.confirm(`Delete ${summary}? This cannot be undone.`)) return;

  const done = withBusy(event.target, "deleting");
  try {
    const { deleted } = await api("/api/data/delete", { method: "POST" });
    forgetSession();
    snack(`Deleted ${deleted.sessions} sessions and ${deleted.events} verdicts. Gone for good.`);
    loadPrivacy();
  } catch (error) {
    snack(error.message, true);
  } finally { done(); }
});

loadStatus();
paintTone();
if (window.location.hash.length > 1) show(window.location.hash.slice(1));
