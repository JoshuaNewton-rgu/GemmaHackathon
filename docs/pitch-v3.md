# HEID DOON — Pitch v3 + Presentation + Demo Plan
*Built from an audit of what is actually in the repo on 26 July 2026, not what the design doc hoped for.
Rubric: **Gemma Integration 30 · Innovation & Impact 30 · Functionality 20 · Presentation & Writeup 20.**
Track: **Motivation & Habits.***

---

## PART 0 — What we actually have (verified, not vibes)

Everything below was read out of the code today. Nothing here is aspirational.

### Shipped and working

| # | Feature | Where | Evidence it's real |
|---|---|---|---|
| F1 | **Contract compiler** — your words → structured rules JSON | `core/contract.py`, `prompts.CONTRACT_COMPILER` | `python -m heiddoon contract "..."` prints it |
| F2 | **Semantic screen/camera verdicts** | `core/verdict.py` | 6/6 on synthetic hard cases incl. lecture-vs-cats |
| F3 | **Automatic server-side watching** | `autopilot.py` (185 lines) | runs while the app is behind another window; perceptual-hash skip means an unchanged screen costs **zero** model calls |
| F4 | **Semantic work-diff** — progress / padding / stalled | `core/diff.py`, `watchers/artifact.py` | mtime-polled, so an untouched file is never re-judged |
| F5 | **Handwriting** — photo of the page → transcribed → *diffed as text* | `core/notes.py` | paper and file go down the same code path, no special cases |
| F6 | **Idle inference** — no input + unchanged screen | `watchers/idle.py` | free; **no model call**, because paying 15s of inference to learn "nothing happened" is a joke |
| F7 | **The Bouncer** — break earned with one retrieval question from *your own* notes | `core/bouncer.py` | falls back to topic-level Qs, deterministic key-point grading when the API is down |
| F8 | **Receipt + drift autopsy + learner model** | `core/receipt.py` | learner model persists and *merges* conservatively across sessions |
| F9 | **Web app**, 5 tabs, Material 3, SSE live stream | `web/` (1,778 lines) | Contract · Watch · Receipt · History · Privacy |
| F10 | **Data rights** — export everything as JSON, delete everything | `store.py`, `/api/export`, `/api/data/delete` | one button each |
| F11 | **Two front ends, one `Session`** | `core/session.py` | CLI watcher + web app on the same SQLite DB, simultaneously |
| F12 | **`doctor`** — proves the model, the handle, and the latency budget | `cli.py` | also warns when one verdict is slower than your cadence |
| F13 | **`capture`** — build the real test set in minutes, model-verified at capture time | `capture.py` | |
| F14 | **The eval that refuses to lie** | `evaluate.py` | see below — this is a scoring feature, not plumbing |

**8 prompt templates → 7 distinct Gemma jobs**, all schema-constrained: contract, verdict, artifact diff, page read, quiz-from-notes, quiz-from-topic, grade, receipt. Every prompt is version-stamped (`2026-07-26.2`) and that version is written into every eval result.

**84 tests pass in 7 seconds**, no network, no model, no GPU. *(The README still says 42 — fix that line, it undersells us by half.)*

### The three principles, enforced in code rather than requested in a prompt

- **Autonomy** — the compiler is forbidden from adding a restriction you didn't ask for; unknown signals are dropped, not silently honoured.
- **Compassion** — exclamation marks and shaming words are stripped by regex in `core/verdict.py:21-25`. Model unreachable → verdict defaults to **on task**, because a false accusation costs more trust than a missed drift. An unreadable page photo is *not logged as an event* — holding a camera badly says nothing about your work. The "show me your page" card carries no verdict, so **being asked can't lower your score, and neither can ignoring it**.
- **Truth** — word counts are computed in Python and override the model. A "progress" verdict on a file that *shrank* is overridden. A focus score more than 25 points off what the event log supports is overridden by arithmetic.

### The four things the eval does that are worth a slide on their own

1. **Refuses to write a results file when the provider is the mock.** You cannot accidentally submit fake numbers.
2. **Scores synthetic mock-ups separately from real captures**, and keeps synthetics out of the headline — a rendered mock-up of a video page gets *read as text* by a vision model, so it proves the pipeline runs and nothing whatsoever about screen understanding.
3. **Counts the frames that didn't run.** A flattering `6/6` cannot hide 12 cases that never executed.
4. **Separates false accusations from missed drift**, because they are not equally bad. A wrong nudge teaches you to distrust the app; a distrusted app gets uninstalled.

### 🔴 The one blocking gap — fix this before anything else

`python -m heiddoon capture --list` says: **0 real frames captured, 12 to go.**
`eval_results.json` headline is **0/1** — and that one "real" frame was a screenshot of *VS Code*, mislabelled as a lecture video. The model correctly said "you are writing software, not studying thermodynamics," and got scored wrong for being right.

So today's honest headline number is: **nothing quotable.** The harness is working as designed — it's refusing to let you quote the flattering 6/6.

**The fix is ~15 minutes**, and it's the highest-value 15 minutes available to you:

```bash
python -m heiddoon capture real_lecture_video.png     # a real lecture, real video site
python -m heiddoon capture real_entertainment.png     # same site, cats
python -m heiddoon capture real_wrong_module_pdf.png  # someone else's module
python -m heiddoon capture real_notes_editor.png      # your actual notes file
python -m heiddoon capture real_social_feed.png
python -m heiddoon capture real_phone_in_hand.jpg --camera
python -m heiddoon capture real_at_desk.jpg --camera
python -m heiddoon eval --out eval_results.json
```

Seven frames buys you a real headline number **including the two cases that defeat every blocker on the market**, plus your first camera coverage. Everything in this pitch marked `[NUMBER]` gets filled from the `QUOTABLE NUMBER` line. Do not improvise it. The harness went to a lot of trouble to stop you.

### Honest limits (say these before a judge finds them)

- Local inference doesn't work on *this* laptop: `gemma4:e4b` crashes on Intel Arc (GGML scheduler assertion), `gemma4:12b` needs 77s per vision call on CPU. **The live demo is hosted `gemma-4-31b-it`.** Never say "no cloud" on stage.
- Median verdict latency **15.1s** (max 17.6s). Fine at the web app's 60s auto-cadence; tight against the CLI watcher's 20s. `doctor` warns you.
- Zero camera frames in the eval so far. Two captures fixes it.
- Idle detection is Windows-only; elsewhere it assumes you're present, which is the safe direction.
- The learner model persists, but that adaptation *works* is untested — hours of data, not weeks. Say "untested," it costs nothing.

---

## PART 1 — The pitch (2:30, with cut-lines for 90s)

> Delivery notes: the jokes are load-bearing — they're what makes a surveillance-shaped product feel
> like a friend. Land them dry. If a laugh doesn't come, keep moving; never repeat a punchline.

### 0:00–0:20 · Hook
> "Quick show of hands: who here has ever opened a lecture recording, and then, forty minutes later, discovered they know a *concerning* amount about how bees make honey?
>
> *[wait for hands, put your own up]*
>
> Right. Every study tool in this building can answer a question. **None of them are in the room at 11pm when the deadline is in nine hours and you open one new tab.** Heid Doon is. And it doesn't just watch your screen — it reads your **work**."

### 0:20–0:40 · The contract *(autonomy)*
> "A session starts with a contract, not a login. What I'm studying, **why it matters to me** — in my words — and my own rules. Lectures allowed. Docs allowed. And I point it at the file I'm actually working in.
>
> Note who wrote the rules. **I did.** Heid Doon just holds me to them. This is the difference between a study partner and a hall monitor, and it's about forty lines of code."

*[click **Heid doon →** — contract compiles live]*

### 0:40–1:10 · The semantic moment *(never cut this — it's the Gemma-necessity beat)*
> "I open YouTube." *[lecture tab]* "…**Nothing happens.**
>
> That silence is the product. It read the screen, saw a thermodynamics lecture, checked my contract, and let it through. A blocker would have thrown me off my own study material.
>
> Now — same website. Different meaning." *[cat tab; nudge fires]*
>
> "'Cat compilation. You said this hour was for entropy.' No exclamation mark — I'll come back to that.
>
> **One website, two verdicts.** Window titles can't do that. Blocklists can't do that. A multimodal model judging meaning against *my* stated goal can. That's not Gemma being used — that's Gemma being **the only way this works at all.**"

### 1:10–1:40 · The phone answer *(say it before a judge does)*
> "Now. The objection every one of you is holding: *nobody procrastinates on their laptop anymore.* Correct. Watch."
>
> *[pick up your actual phone, look at it]*
>
> "'Phone in hand, eyes off screen.' Same model, camera frame.
>
> But cameras can be fooled — so I put it under the desk. Here's the part I'm actually proud of: Heid Doon snapshots my notes file and **Gemma diffs it semantically**. Not `+40 words` — 'two worked problems, one of them wrong.' Twenty minutes of TikTok is an **empty diff**. Twenty minutes of typing nonsense to game it comes back as **'padding.'**
>
> **You can hide a phone from a camera. You cannot hide an empty page.**
>
> And if you work on paper — we photograph the page, transcribe it, and diff the *transcriptions*. Handwriting goes down the exact same code path. No special cases." `[CUT this last line for 90s]`

### 1:40–2:00 · Kindness, in code *(the differentiator judges won't expect)*
> "Procrastination isn't laziness, it's emotion regulation — you avoid the thing that makes you feel bad, the avoidance produces shame, and the shame buys the next avoidance. So shame is the one thing this app is not allowed to do.
>
> And 'the prompt says be kind' is not a guarantee, it's a **hope**. So exclamation marks and shaming words are stripped by a regex. If the model calls you lazy, the model gets overruled. If the API goes down mid-session, the verdict defaults to **'on task'** — because falsely accusing you costs more than missing one drift.
>
> Want a break? You don't get blocked, you get **negotiated with**: answer one recall question generated from your own notes and you're out. The price of a break is a rep of retrieval practice. Which is, annoyingly, studying." `[CUT the last two sentences for 90s]`

### 2:00–2:20 · The receipt + why Gemma
> "Sessions end with a receipt. Focus score — computed in Python, not vibed by the model. A drift autopsy: 'you go 25 minutes in, always right after the derivations — that's task aversion, not distraction.' And a learner model that puts tomorrow's hardest material **before** your danger zone, with a break already scheduled, so there's nothing left to steal.
>
> **One open model family doing seven jobs**: screen vision, camera presence, semantic work diffs, handwriting, quiz generation, grading, and the autopsy. Every one a schema-constrained call. Take Gemma out and there is no app — there's a folder.
>
> And it has to be **open weights**. A closed cloud API watching a student's screen and webcam is surveillance with a subscription. On weights you can run yourself, it's a study partner. `heiddoon watch` runs the whole loop locally against Ollama, frames discarded, verdicts only. There is **no column in our database that can hold a frame** — that's not a promise in a privacy policy, it's a schema."

### 2:20–2:30 · The number + close
> "Labelled test set of real captures: **[NUMBER — exactly as `heiddoon eval` prints it]**, including lecture-versus-cats and phone-in-hand. Median **15 seconds** a verdict. 84 tests, no GPU needed. And I can tell you **which ones it got wrong and why**, because the harness reports false accusations separately from missed drift and physically refuses to print a number from mock data.
>
> Screen-watching is a commodity. **A behavioural loop that reads your real progress isn't.**
>
> Heid doon."

---

## PART 2 — Slide-by-slide (10 slides, ~15s each)

Rule: **the app is the presentation.** Slides exist so that when the demo dies you're still giving a talk. One idea per slide, no paragraphs, no build animations.

| # | On screen | You say | Rubric |
|---|---|---|---|
| 1 | **HEID DOON** · *It reads your work, not just your screen.* · Scots for "head down" | Hook — the bees | Present |
| 2 | The honey-bee tab, big | "Every tool answers questions. None are there at 11pm." | Innov |
| 3 | The contract JSON, live from your words | "I wrote the rules." | Innov (autonomy) |
| 4 | **Two YouTube screenshots. One verdict each. Same site.** | The semantic beat | **Gemma ✓✓** |
| 5 | `progress · padding · stalled` | "You can't hide an empty page." | **Innov ✓✓** |
| 6 | The regex from `verdict.py:21` on screen | "Kindness is not a prompt, it's a rule." | Innov |
| 7 | Loop diagram: Contract→Watch→Intervene→Negotiate→Checkpoint→Receipt→Adapt | "Five mechanics, one `Session`. Not five demos." | Func |
| 8 | The eval table + the 4 anti-lying rules | "Here's what it got wrong, and why." | **Func ✓✓** |
| 9 | Privacy tab: no frame column, export, delete | "Open weights are the ethics." | **Gemma ✓✓** |
| 10 | **[NUMBER]** · 7 Gemma jobs · 84 tests · `heid doon.` | Close | Present |

Slide 6 is the sleeper. Every team will claim their AI is kind. You'll be the one showing the regex that enforces it.

---

## PART 3 — How this banks each criterion

**Gemma Integration — 30.** Argue **necessity, not usage.** (a) The hard cases are unsolvable by titles or blocklists — a blocker scores 0 on lecture-vs-cats, and we have the labelled frames to prove it. (b) **Seven distinct schema-constrained jobs**; there is no non-model path that "is" the app. (c) **Open weights are load-bearing, not a bonus**: screen+camera watching is only ethically shippable on weights the student can run, and we enforce that structurally — the privacy banner is *generated from the live config*, so a hosted backend physically cannot render the local-only promise. (d) The size ladder is architecture: E4B where privacy and latency live, larger where reasoning lives, one provider seam between them.
*Say out loud:* today's demo is hosted, and why. Judges forgive a hardware limit. They do not forgive being told frames stayed local when they didn't.

**Innovation & Impact — 30.** Brief-fit is 1:1 — nudging at the right moment (F2/F3), adapting to progress (F4/F8), holding you to *your own* goals (F1/F7). Two genuinely novel pieces: **progress-from-artifact accountability** (F4 — device-independent by construction) and **drift-autopsy avoidance profiling** (F8). Grounded in the actual literature: emotion-regulation over time-management (Pychyl & Sirois), self-forgiveness reducing the *next* lapse (Wohl et al.), retrieval practice as the price of a break (Roediger & Karpicke), autonomy support over surveillance (SDT). Prior art named voluntarily — Rewind and Screenpipe do perception; nobody ships the *loop* for learners.

**Functionality — 20.** End-to-end in one app, two front ends over one `Session` and one database, running simultaneously with live SSE. 84 tests, no network/model/GPU. `doctor` for reproducibility. A four-rung demo failure ladder. Judges can reproduce every number with two commands.

**Presentation & Writeup — 20.** Headings mirror the rubric verbatim. The number is quoted exactly as printed, misses included. An honest "didn't ship" section — in a one-day format, honesty *is* a scoring strategy, and our harness makes dishonesty impossible anyway. Which is a much better story than a higher number.

---

## PART 4 — The demo plan

### T-30 min · pre-flight (do all of it, in order)

```bash
python -m heiddoon doctor          # model reachable + latency budget. If this fails, stop and fix.
python -m heiddoon eval            # confirm your real number one last time
pytest -q                          # 84 passed — a nice thing to have on screen if asked
```

Then set the demo cadence — **the defaults are tuned for real use, which is far too patient for a stage:**

```bash
HEIDDOON_AUTO_CADENCE_S=25         # 60s of silence is death in a live demo (15s verdicts, so not lower)
HEIDDOON_NOTES_PROMPT_EVERY_MIN=1  # forces the "show me your page" card to appear
```

**Put both back before you submit or record anything.** A 1-minute page prompt is exactly the pestering the app is designed not to do, and someone will notice.

Physical checklist:
- [ ] Two browser tabs pre-loaded and paused: **thermo lecture** and **cat compilation**. Pre-loaded. Not "I'll search for it."
- [ ] `notes_thermo.md` open in your editor, contracted, with a **paragraph on the clipboard ready to paste** (a real one) and a **junk paragraph** ready for the padding beat.
- [ ] A handwritten page. Actually handwritten. Ideally slightly messy — a clean one looks staged.
- [ ] Your real phone on the desk, face up.
- [ ] **Notifications off. All of them.** A Slack message mid-demo about lunch will get the biggest laugh of your life and cost you the room.
- [ ] Backup recording on the desktop, one click from playing.
- [ ] Hotspot on. Venue Wi-Fi has never once held.
- [ ] Battery. Yes, really.

### The 90-second run (rehearse ×3 with a timer)

| t | You do | It does | Beat |
|---|---|---|---|
| 0:00 | Paste the contract in your own words, hit **Compile my rules** | Structured rules appear, ~2s | Autonomy |
| 0:10 | **Start watching**, then **Watch automatically** | Autopilot on, server-side | Functionality |
| 0:15 | Switch to the **lecture** tab. Say nothing. Let it sit. | **Silence.** | The hard one |
| 0:30 | Switch to the **cat** tab | Nudge card, no exclamation mark | **The money shot** |
| 0:45 | Pick up your phone and look at it | Presence verdict / page card | The phone answer |
| 0:55 | Paste the junk paragraph into your notes, save | **"padding"** | Truth |
| 1:05 | Paste the real paragraph, save | **"progress, +N words"** | Truth |
| 1:15 | **Ask for a break** → answer badly, then properly | Question from *your* notes → granted | Negotiation |
| 1:30 | **Finish** → Receipt tab | Focus score, autopsy, tomorrow | The close |

Two tricks that make this reliable:
1. **Press "Check something now" for every screen beat.** Autopilot proves it works unattended; the button makes it happen *when you're pointing at it*. Show autopilot running in the corner and drive the beats yourself. This is not cheating — the same code path runs either way, and you can say so.
2. **Talk through the 15-second verdict latency, don't wait through it.** Fill it: "it's reading the frame now — locally, if your laptop has a GPU; today mine doesn't, so this one's hosted." You've converted dead air into the honesty beat.

### The silence problem

Your single best beat is the lecture tab, where **nothing happens** — and "nothing happens" is invisible on a stage. Narrate it:

> "Watch the log. Nothing. It looked at YouTube and decided to leave me alone. Any blocker in this room just interrupted my studying."

Point at the empty log. Give it a full beat. Then switch to cats.

### Failure ladder (rehearse rung 2 — you will probably need it)

1. **Live web app.** The plan.
2. **`python -m heiddoon eval` in a terminal, live.** The labelled set scoring in front of them is a *real* demo, not an apology. Say: "the app is being shy, so let's watch it score the labelled set instead — same code path, and you can run this yourself." Judges respect a terminal.
3. **Backup recording**, narrated live by you.
4. **The slides + the eval JSON on screen.** Still a coherent talk. This is why the slides exist.

If the model returns garbage mid-demo, that is *also* a beat: "and there's the fallback — model unreachable, so it defaults to *on task*. It would rather miss a drift than accuse you wrongly." You cannot lose that exchange.

### Timing discipline

If you're at 2:00 with the receipt unshown: skip the Bouncer, go straight to the receipt. **Never** cut the lecture-vs-cats beat, and never cut the number. Those are 60 of the 100 points.

---

## PART 5 · Q&A ammo

| They ask | You say |
|---|---|
| **"Isn't this just surveillance?"** | "You wrote the rules, and you can hit Delete Everything in the Privacy tab while I'm standing here. There's no column in our schema that can hold a frame — the frame lives as a Python object for one judgment and gets dropped. What persists is a sentence about what was seen. And the cloud version *would* be creepy — which is precisely why the weights being open is a feature and not a footnote." |
| **"A blocklist would do this."** | "It would also block your lecture. That's the whole demo. Titles lie: one site is a lecture *and* cats, and a PDF can be the wrong module's PDF. That's a judgment about meaning, which is a multimodal model's job." |
| **"What if they just use their phone?"** | "Three layers, and they're stacked deliberately: the camera catches the glance, idle inference catches the absence for free, and the work-diff catches the *truth*. The diff is device-independent — it measures output, not activity. Procrastinate on any device you like; twenty minutes of it is still an empty page." |
| **"Couldn't they fake the notes file?"** | "You'd be typing filler into your own notes to fool your own study app — at which point you are, at minimum, typing about thermodynamics. And the diff is semantic, so it comes back 'padding.' Gaming it costs more effort than working." |
| **"Is it really local?"** | *Answer with what `doctor` printed today.* "The architecture has one provider seam with a local backend and a hosted one. `heiddoon watch` runs entirely local on hardware that can serve the weights fast enough. This laptop can't — E4B crashes on Intel Arc and 12B takes 77 seconds a vision call — so today is hosted, and I'd rather tell you than have you find out. The privacy property belongs to the open weights, not to our cleverness, which is exactly why it survives where we run them." |
| **"Rewind / Screenpipe exist."** | "They do, they're good, and they're in our writeup. Screen perception is a commodity. The product is the loop: contract → verdict → negotiation → work-diff → autopsy → adapted plan. Nobody ships that for learners." |
| **"Your headline number is small."** | "It's small because the harness refuses to count the synthetic frames — a rendered mock-up of a video page gets read as *text* by a vision model, so it scores near-perfectly and measures nothing. I could have shown you 6/6 this morning. It would have been meaningless. Here's the real number, and here's the one it got wrong." *(This answer is worth more than a bigger number. Deliver it with relish.)* |
| **"What didn't you ship?"** | "Nudge-style adaptation and audio check-ins: designed, not built. Idle detection is Windows-only. And the learner model persists, but I can't claim the *adaptation* is validated — that needs weeks of data and I've had hours." |
| **"Why the name?"** | "Scots for 'head down.' It's what your gran says to you in May. Also, every domain with a normal name was taken." |

---

## Two lines that have to land

> **"It reads your work, not just your screen."**
> **"You can hide a phone from a camera. You can't hide an empty page."**

Everything else is negotiable. `heid doon.`
