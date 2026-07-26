# Heid Doon: you can hide a phone from a camera, but you can't hide an empty page

### Every other focus app watches your screen. Heid Doon measures the work - the diff in your document, typed or handwritten - so twenty minutes of scrolling shows up as an empty page whichever device you scrolled on. Gemma 4 perceives; 16 readable fuzzy rules decide, so every interruption ships with the arithmetic that caused it.

Team: Joshua Newton & Jordan Newlands · Repo: [github.com/JoshuaNewton-rgu/GemmaHackathon](https://github.com/JoshuaNewton-rgu/GemmaHackathon)

---

### The problem

- **Procrastination is an emotion-regulation failure, not a time-management one** (Pychyl & Sirois). You avoid the task that makes you feel bad, the avoidance produces shame, and the shame buys the next avoidance.
- **The moment that decides a grade isn't a question being answered.** It's 11pm, a deadline in nine hours, and one new tab. Nothing mainstream is present at that moment.
- **Blockers get uninstalled within a week, because they're dumb.** They cannot tell a lexical-analysis lecture on YouTube from cat videos on YouTube. They punish instead of helping, and they block your own study material.

### The solution

**Heid Doon** (Scots: *head down*). One loop: **Contract → Watch → Intervene → Negotiate → Checkpoint → Receipt → Adapt.**

Three commitments, each enforced in code rather than requested in a prompt:

- **It works for you, not on you.** *You* write the contract: the task, why it matters, and your own rules for what counts as on-task. The compiler is forbidden from adding a restriction you didn't ask for, and the 16 rules that decide when you get interrupted are ones you can read, reweight, or delete.
- **It adapts to you.** Sessions end with a drift autopsy — *"you drift ~25 minutes in, always to video, right after the derivations; that's task-aversion, not distraction"* — and the learner model schedules tomorrow's hardest material *before* your danger zone, with a break already planned so there's nothing left to steal.
- **It holds you to your own contract, without shaming you for it.** Word counts are computed in Python and override the model's guess; a "progress" verdict on a file that *shrank* is overridden; the focus score is arithmetic over the event log, and when the model's number disagrees with it by more than 25 the arithmetic wins. But exclamation marks and shaming words are stripped by regex in `core/verdict.py`, because asking a model not to shame someone is a request, not a rule — and when the model is unreachable the verdict defaults to **on task**.

Five signals feed one loop:

| Signal | Answers | Cost |
|---|---|---|
| **Screen** | What are you looking at, and does it mean what your contract allows? | one vision call, **zero when the screen hasn't changed** (perceptual hash) |
| **Camera** | Are you here? Is there a phone in your hand? | one vision call, at most once per interval |
| **Artifact** | Did the work actually move: progress, padding, or stalled? | one text call, only when the file changed |
| **Page** | What's on your paper notes, and has it grown? | one vision call, transcribed then diffed as text |
| **Idle** | Are you at the machine at all? | **free, no model call.** Paying 15s of inference to learn nothing happened is a joke |

- **The work-diff is the part that matters**, because it answers the objection every screen-watcher fails: *what if I procrastinate on my phone?* It's device-independent by construction. Twenty minutes of scrolling shows up as an empty diff.
- **Handwriting goes down the identical code path.** Photograph the page, transcribe it, diff the *transcriptions*. No special cases.
- **Breaks are negotiated, not blocked.** Ask for one and the Bouncer generates a retrieval question from *your own notes*. The price of a break is a rep of retrieval practice, which is annoyingly just studying.
- **The streak cannot be broken.** Missed days are drawn hatched rather than resetting you to zero: *a lapse is not a relapse.* Every other app ships the streak as a loss-aversion trap, which is precisely backwards — self-forgiveness after a lapse is what predicts *less* procrastination next time (Wohl et al.), and shame is what predicts more. It's the one number you cannot lose by having a bad day.
- **The camera never spends an interruption on something we already know.** If the tracked file moved, you aren't asked — the diff already answered it. It's a card, never a modal; "not now" is respected and isn't recorded; an unreadable photo isn't logged at all, because holding a camera badly says nothing about whether you're working.

### How we used Gemma 4: necessity, not usage

- **The hard cases are unsolvable without a multimodal model.** Lecture-vs-cats on the same site, the wrong module's PDF, a study-group chat that's genuinely about the problem set. A blocklist scores zero on these by construction. Judging *meaning against a personal contract* is the product, and it's Gemma 4's vision doing it.
- **12 prompt templates, 7 distinct schema-constrained jobs:** contract compilation, frame verdict, artifact diff, page transcription, quiz-from-notes, quiz-from-topic, answer grading, receipt/learner-model update. All structured JSON. **There is no non-model code path that "is" this app.**
- **Gemma perceives; it does not adjudicate.** On a mentor's suggestion mid-sprint we replaced the binary `on_task: bool` with an **explainable fuzzy rule layer** (Zadeh/Mamdani):
  - Gemma extracts *observations*: topic match, is-this-your-own-work, padding, presence, confidence.
  - **16 English rules decide what happens**, parsed from those sentences at import: `IF topic_match is low AND drift is long AND confidence is not low THEN nudge is firm`.
  - **Why it matters:** the old `reason` string was written *after* the model decided. Post-hoc narration with no causal link, and nothing a student could contest. Now every interruption ships with the arithmetic that caused it, and `IF confidence is low THEN nudge is silent` is a rule you can read, reweight, or delete.
- **Open weights are the ethics, structurally.** A screen-and-camera watcher on a closed API is surveillance with a subscription. Because Gemma's weights are open there *is* an alternative: `heiddoon watch` runs the whole loop against Ollama, frames judged and discarded.
  - **There is no column anywhere in our schema that can hold a frame.** Not a privacy policy, a schema.
  - The privacy banner is **generated from the live config**, so a hosted backend physically cannot render the local-only claim.
  - One button exports everything as JSON; one deletes everything. Data rights you can exercise, not request.

### Architecture

- **One `Session` object makes five mechanics a loop, not five demos.** Everything goes through it, so the event log is an account of what occurred, and the receipt is generated from it rather than from a plausible story about it.
- **Two front ends, one Session, one SQLite database.** The web app and the CLI watcher run simultaneously, with the UI streaming the watcher's verdicts over SSE.
- **Autopilot watches server-side**, so it keeps working while the app is behind another window, which is the point: the interesting frames are the ones where the app isn't in front.
- **One provider seam** (hosted API · Ollama · mock) decides where the weights run. Nothing above it knows the difference.
- **152 tests. No network, no model, no GPU.** The loop is testable because the perception is behind a seam.

### The eval refuses to flatter us

Three rules are enforced in the harness, because each is a way a demo number quietly becomes a lie:

- **Mock output is never written to a results file.** If the provider is the mock, the harness refuses to produce a number at all.
- **Synthetic frames are scored separately from real ones.** A rendered mock-up of a video page is read by the model as *text*; it proves the pipeline runs and nothing whatsoever about screen understanding. Only real captures appear in the headline.
- **Frames that didn't run are counted as not-run**, so `6/6` cannot hide twelve cases that never executed.

The report separates **false accusations from missed drift** — they are not equally bad, and a single accuracy number pretends they are — and records the prompt version, so any figure traces back to the wording that produced it.

### Known limits

- **Local inference doesn't work on this laptop.** `gemma4:e4b` crashes on Intel Arc (GGML scheduler assertion); 12B needs **77s per vision call** on CPU against a 20s cadence. That's why the provider seam exists, and why today's demo is hosted `gemma-4-26b-a4b-it`.
- **The diff can be gamed** by typing filler into your own notes. At which point the model flags padding, and you are, at minimum, typing about sorting algorithms.
- **Idle detection is Windows-only** so far. Elsewhere it returns 0 — "assume they're here", the safe direction.
- **Screen perception has prior art** (Rewind, Screenpipe). The contribution here is the behavioural loop for learners, not the perception.

### What's next

Real-capture eval coverage · cross-session validation of the adaptation · **E2B on-device**, the same open weights and the same privacy, in your pocket.

---
*Reproduce every number: `pip install -e ".[watch,web,dev]"` → `python -m heiddoon doctor` → `python -m heiddoon eval` → `pytest -q`.*
