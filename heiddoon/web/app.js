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
  busy: false,
};

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

function toast(message, isError = false) {
  const node = el("div", `toast${isError ? " err" : ""}`, message);
  document.body.appendChild(node);
  setTimeout(() => node.remove(), isError ? 7000 : 3500);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return response.json();
}

/* Long model calls are the normal case, not the exception — a local vision call
   can take over a minute. So every action that waits shows it, and blocks a
   second click rather than queueing an identical request. */
function withBusy(button, label) {
  const original = button ? button.textContent : null;
  state.busy = true;
  $("pulse").classList.add("busy");
  $("watcher-label").textContent = label;
  if (button) { button.disabled = true; button.textContent = "…"; }
  return () => {
    state.busy = false;
    $("pulse").classList.remove("busy");
    $("watcher-label").textContent = "watching";
    if (button) { button.disabled = false; button.textContent = original; }
  };
}

/* ── navigation ─────────────────────────────────────────────────────────── */

function show(name) {
  document.querySelectorAll(".screen").forEach((node) => node.classList.remove("active"));
  $(`scr-${name}`).classList.add("active");
  document.querySelectorAll(".nav-btn").forEach((node) =>
    node.classList.toggle("active", node.dataset.screen === name));
  if (name === "history") loadHistory();
}
document.querySelectorAll(".nav-btn").forEach((node) =>
  node.addEventListener("click", () => show(node.dataset.screen)));

/* ── status: the header must describe the real configuration ────────────── */

async function loadStatus() {
  try {
    const status = await api("/api/status");
    const badge = $("model-badge");
    $("model-text").textContent = status.provider_ready ? status.provider : "model unavailable";
    badge.classList.toggle("down", !status.provider_ready);
    badge.classList.toggle("mock", !!status.mock);
    if (status.mock) $("model-text").textContent = "MOCK — no model is running";
    $("privacy-text").textContent = status.privacy_line;
    $("privacy-strip").classList.toggle("hosted", !status.local_inference);
    if (!status.provider_ready) toast(status.provider, true);
  } catch (error) {
    $("model-text").textContent = "server unreachable";
    $("model-badge").classList.add("down");
  }
}

/* ── contract ───────────────────────────────────────────────────────────── */

const EXAMPLE = `I'm revising thermodynamics chapter 4 (entropy) until 12:30. Exam Friday — no all-nighter this time. Lecture videos and PDFs about thermodynamics are fine, music is fine, my study group chat is fine when we're discussing the problem set. No social media, no entertainment videos. Track notes_thermo.md. Camera presence on. Kind but sharp.`;

$("btn-example").addEventListener("click", () => { $("contract-text").value = EXAMPLE; });

$("btn-compile").addEventListener("click", async (event) => {
  const text = $("contract-text").value.trim();
  if (!text) { toast("Write your rules first.", true); return; }
  const done = withBusy(event.target, "compiling");
  try {
    const { contract, repairs } = await api("/api/contract/compile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    state.contract = contract;
    renderContract(contract);
    if (repairs && repairs.length) toast(`Compiled, with ${repairs.length} field(s) repaired.`);
  } catch (error) {
    toast(`Could not compile: ${error.message}`, true);
  } finally { done(); }
});

function renderContract(contract) {
  $("c-task").textContent = contract.task || "(none)";
  $("c-why").textContent = contract.why || "(no reason given — nudges will be plainer without one)";
  const fill = (id, items) => {
    const host = $(id);
    host.innerHTML = "";
    (items && items.length ? items : ["—"]).forEach((item) => host.appendChild(el("span", "chip", item)));
  };
  fill("c-allowed", contract.allowed);
  fill("c-blocked", contract.blocked);
  fill("c-signals", contract.signals);
  $("contract-preview").classList.remove("hidden");
}

$("btn-edit").addEventListener("click", () => $("contract-preview").classList.add("hidden"));

$("btn-start").addEventListener("click", async (event) => {
  const done = withBusy(event.target, "starting");
  try {
    const data = await api("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contract: state.contract }),
    });
    state.sessionId = data.session_id;
    state.startedAt = Date.now();
    state.events = [];
    $("session-id").textContent = `#${data.session_id}`;
    $("session-task").textContent = data.contract.task;
    $("nav-session").disabled = false;
    $("nav-receipt").disabled = false;
    renderArtifactButtons(data.contract.artifacts || []);
    subscribe(data.session_id);
    startClock();
    show("session");
  } catch (error) {
    toast(`Could not start: ${error.message}`, true);
  } finally { done(); }
});

/* ── the clock ring ─────────────────────────────────────────────────────── */

function startClock() {
  const tick = () => {
    if (!state.startedAt) return;
    const seconds = Math.floor((Date.now() - state.startedAt) / 1000);
    const minutes = Math.floor(seconds / 60);
    $("clock").textContent = `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
    // A 50-minute session fills the ring; longer just stays full.
    const fraction = Math.min(1, seconds / (50 * 60));
    $("ring-fg").setAttribute("stroke-dashoffset", String(490 * (1 - fraction)));
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
  };
}

function addFeedRow(event) {
  const feed = $("feed");
  feed.querySelector(".feed-empty")?.remove();

  let kind = "work";
  let icon = "◆";
  if (event.on_task === true) { kind = "ok"; icon = "✓"; }
  else if (event.on_task === false) { kind = "bad"; icon = "!"; }

  const row = el("div", `verdict ${kind}`);
  row.appendChild(el("div", "ico", icon));

  const body = el("div", "body");
  const detail = event.detail || {};
  if (event.kind === "diff") {
    body.appendChild(el("div", "what", `${event.seen} — ${detail.verdict} (${detail.delta_words >= 0 ? "+" : ""}${detail.delta_words} words)`));
    body.appendChild(el("div", "why", detail.quality_note || detail.summary || ""));
  } else if (event.kind === "quiz") {
    body.appendChild(el("div", "what", detail.pass ? "Break earned" : "Break not earned"));
    body.appendChild(el("div", "why", detail.feedback || ""));
  } else {
    body.appendChild(el("div", "what", event.seen || event.kind));
    body.appendChild(el("div", "why", detail.nudge || detail.reason || ""));
  }
  row.appendChild(body);

  const meta = el("div", "meta");
  meta.appendChild(el("div", "time", new Date(event.at * 1000).toLocaleTimeString()));
  if (detail.latency_s) meta.appendChild(el("div", "lat", `${detail.latency_s}s`));
  if (detail.confidence === "low") meta.appendChild(el("div", "lat", "low conf."));
  row.appendChild(meta);

  feed.prepend(row);

  if (event.on_task === false && (detail.nudge || "").length) showNudge(detail.nudge, event.seen);
}

/* ── frames ─────────────────────────────────────────────────────────────── */

async function judgeBlob(blob, kind, button) {
  const done = withBusy(button, kind === "camera" ? "reading the room" : "reading the screen");
  try {
    const form = new FormData();
    form.append("file", blob, "frame.png");
    await api(`/api/session/${state.sessionId}/frame?kind=${kind}`, { method: "POST", body: form });
  } catch (error) {
    toast(`Could not judge that frame: ${error.message}`, true);
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

$("btn-webcam").addEventListener("click", async () => {
  try {
    state.webcamStream = await navigator.mediaDevices.getUserMedia({ video: true });
    const video = $("webcam");
    video.srcObject = state.webcamStream;
    video.classList.remove("hidden");
    $("btn-snap").disabled = false;
  } catch (error) {
    toast(`No camera: ${error.message}`, true);
  }
});

$("btn-snap").addEventListener("click", async (event) => {
  const video = $("webcam");
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
  await judgeBlob(blob, "camera", event.target);
});

/* ── work-diff ──────────────────────────────────────────────────────────── */

function renderArtifactButtons(artifacts) {
  const host = $("artifact-actions");
  host.innerHTML = "";
  if (!artifacts.length) {
    host.appendChild(el("div", "note", "This contract names no file to track — paste two versions below instead."));
    return;
  }
  const button = el("button", "btn btn-primary btn-sm", `Check ${artifacts.join(", ")} on disk`);
  button.addEventListener("click", async () => {
    const done = withBusy(button, "reading your file");
    try {
      const { diffs } = await api(`/api/session/${state.sessionId}/artifact-check`, { method: "POST" });
      const unseen = Object.entries(diffs).filter(([, value]) => value === null).map(([key]) => key);
      if (unseen.length) toast(`Baseline recorded for ${unseen.join(", ")} — check again after some writing.`);
    } catch (error) {
      toast(`Could not check the file: ${error.message}`, true);
    } finally { done(); }
  });
  host.appendChild(button);
}

$("btn-diff").addEventListener("click", async (event) => {
  const before = $("diff-before").value;
  const after = $("diff-after").value;
  if (!before.trim() && !after.trim()) { toast("Paste two versions of your notes.", true); return; }
  const done = withBusy(event.target, "reading your work");
  try {
    await api(`/api/session/${state.sessionId}/diff`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ before, after, minutes: 20 }),
    });
  } catch (error) {
    toast(`Could not judge that delta: ${error.message}`, true);
  } finally { done(); }
});

/* ── nudge + bouncer ────────────────────────────────────────────────────── */

function showNudge(line, seen) {
  $("nudge-line").textContent = line;
  $("nudge-seen").textContent = seen ? `Seen: ${seen}` : "";
  $("ov-nudge").classList.add("open");
}
$("btn-backtoit").addEventListener("click", () => $("ov-nudge").classList.remove("open"));
$("btn-open-bouncer").addEventListener("click", () => {
  $("ov-nudge").classList.remove("open");
  askForBreak();
});
$("btn-break").addEventListener("click", askForBreak);
$("btn-close-bouncer").addEventListener("click", () => $("ov-bouncer").classList.remove("open"));

async function askForBreak() {
  const notes = $("diff-after").value.trim() || null;
  $("bouncer-question").textContent = "…";
  $("grant-msg").classList.add("hidden");
  $("bouncer-answer").value = "";
  $("ov-bouncer").classList.add("open");
  try {
    const { question } = await api(`/api/session/${state.sessionId}/break`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes }),
    });
    $("bouncer-question").textContent = question;
  } catch (error) {
    $("bouncer-question").textContent = "Could not think of a question just now.";
    toast(error.message, true);
  }
}

$("btn-answer").addEventListener("click", async (event) => {
  const answer = $("bouncer-answer").value;
  const done = withBusy(event.target, "marking");
  try {
    const grade = await api(`/api/session/${state.sessionId}/break/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer }),
    });
    const message = $("grant-msg");
    message.textContent = grade.feedback;
    message.className = `grant ${grade.pass ? "pass" : "fail"}`;
    if (grade.pass) setTimeout(() => $("ov-bouncer").classList.remove("open"), 2600);
  } catch (error) {
    toast(error.message, true);
  } finally { done(); }
});

/* ── receipt ────────────────────────────────────────────────────────────── */

$("btn-finish").addEventListener("click", async (event) => {
  const done = withBusy(event.target, "writing your receipt");
  try {
    const { receipt } = await api(`/api/session/${state.sessionId}/finish`, { method: "POST" });
    renderReceipt(receipt);
    if (state.stream) { state.stream.close(); state.stream = null; }
    if (state.webcamStream) state.webcamStream.getTracks().forEach((track) => track.stop());
    show("receipt");
  } catch (error) {
    toast(`Could not finish: ${error.message}`, true);
  } finally { done(); }
});

function renderReceipt(receipt) {
  const checks = state.events.filter((event) => event.on_task !== null && event.on_task !== undefined
    && (event.kind === "screen" || event.kind === "camera"));
  const drifted = checks.filter((event) => event.on_task === false);
  const diffs = state.events.filter((event) => event.kind === "diff");
  const words = diffs.reduce((total, event) => total + (event.detail.delta_words || 0), 0);

  $("r-score").textContent = receipt.focus_score;
  $("r-checks").textContent = checks.length;
  $("r-drift").textContent = `${drifted.length} drifted`;
  $("r-words").textContent = words >= 0 ? `+${words}` : String(words);
  $("r-quality").textContent = diffs.length ? diffs[diffs.length - 1].detail.verdict : "not checked";
  $("r-elapsed").textContent = Math.floor((Date.now() - state.startedAt) / 60000);
  $("r-autopsy").textContent = receipt.autopsy;
  $("r-tomorrow").innerHTML = `<b>Tomorrow:</b> ${receipt.tomorrow}`;
  $("r-learner").textContent = JSON.stringify(receipt.learner_model, null, 2);

  const timeline = $("r-timeline");
  timeline.innerHTML = "";
  state.events.forEach((event) => {
    const segment = el("div", "seg");
    if (event.kind === "diff") segment.classList.add("work");
    else if (event.on_task === false) segment.classList.add("drift");
    else segment.classList.add("focus");
    segment.title = `${event.kind}: ${event.seen || ""}`;
    timeline.appendChild(segment);
  });
}

$("btn-again").addEventListener("click", () => {
  state.sessionId = null;
  state.events = [];
  $("feed").innerHTML = '<div class="feed-empty">Nothing yet.</div>';
  show("contract");
});

/* ── history ────────────────────────────────────────────────────────────── */

async function loadHistory() {
  try {
    const data = await api("/api/history");
    const host = $("h-sessions");
    host.innerHTML = "";
    if (!data.sessions.length) host.appendChild(el("div", "feed-empty", "No sessions recorded yet."));
    data.sessions.forEach((session) => {
      const row = el("div", "verdict work");
      row.appendChild(el("div", "ico", "#"));
      const body = el("div", "body");
      body.appendChild(el("div", "what", `Session ${session.id}`));
      body.appendChild(el("div", "why", session.ended_at
        ? `focus ${session.focus_score ?? "–"}/100`
        : "still open"));
      row.appendChild(body);
      const meta = el("div", "meta");
      meta.appendChild(el("div", "time", new Date(session.started_at * 1000).toLocaleString()));
      row.appendChild(meta);
      host.appendChild(row);
    });
    $("h-learner").textContent = JSON.stringify(data.learner_model, null, 2);
  } catch (error) {
    toast(error.message, true);
  }
}

loadStatus();
