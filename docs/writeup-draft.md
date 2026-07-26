# Heid Doon — the study companion that catches you procrastinating
## It reads your work, not just your screen: semantic screen verdicts, camera presence, and progress measured from the artifact itself — all on Gemma 4, local-first.

**Track: Motivation & Habits** · Team: [FILL — name(s)] · ~[FILL] words

*(Paste into the Kaggle Writeup editor. Fill every [FILL]. Keep under 1,500 words — this draft is ~1,250 with slots filled. Attach: the notebook (public), the test-set dataset (public), the Gradio share URL.)*

---

### The problem

Study tools that only answer questions are easy to build and easy to ignore — the brief says so, and the research agrees on why. Procrastination isn't a time-management failure; it's an **emotion-regulation failure** (Pychyl & Sirois): we avoid the task that makes us feel bad, the avoidance produces shame, and the shame fuels the next avoidance. The moment that decides a grade isn't a question being answered — it's 11pm, a deadline in nine hours, and one new browser tab. No mainstream study tool is present at that moment. Blockers are (and get uninstalled within a week) because they're dumb: they can't tell a thermodynamics lecture on YouTube from cat videos on YouTube, and they punish instead of helping.

### The solution

**Heid Doon** (Scots: "head down") is a session companion built on three principles: **autonomy** — the student writes the contract (task, why it matters, and *their own rules* for what counts as on-task); **compassion** — nudges are warm, restarts are self-forgiving (Wohl et al.: self-forgiveness after a lapse measurably reduces the next procrastination episode); and **truth** — progress is measured from the *work itself*, not from surveilled activity.

One session: **Contract → Watch → Intervene → Negotiate → Checkpoint → Receipt → Adapt.** Three signals feed the loop. *Screen frames* are judged semantically against the contract — our watcher passes a YouTube lecture and flags cat videos, passes the study-group chat when it's discussing the problem set, flags a PDF from the wrong module. *Camera frames* catch what the screen can't: phone-in-hand, empty chair. And the **work-diff** answers the question every screen-watcher fails: *what if I procrastinate on my phone?* Heid Doon snapshots the student's contracted file and Gemma judges the delta — substance, padding, or stalled. Twenty minutes of phone scrolling is an empty diff. You can hide a phone from a camera; you can't hide an empty page.

Breaks are negotiated, not stolen: the Bouncer asks one retrieval question generated from the student's own notes (retrieval practice — the "cost" of a break is literally learning). Sessions end with a **drift autopsy** — "you drift ~25 minutes in, always to video, right after the derivations; that's task-aversion, not distraction" — and an updated learner model that schedules tomorrow's hardest material *before* the student's personal danger zone, with a break already planned so there's nothing to steal.

### How we used Gemma 4 (and why nothing else would do)

Our claim is **necessity, not usage**. Remove Gemma 4 and Heid Doon is either impossible or unethical:

1. **Semantic multimodal verdicts.** The hard third of our eval — lecture-vs-cats, wrong-module PDF, on-topic chat — is unsolvable by window titles or blocklists. A multimodal model judging *meaning against a personal contract* is the product's core, and it's Gemma 4's vision doing it.
2. **Every mechanic is a structured-output call.** Contract compiler, frame verdicts, work-diff judgments, quiz generation, answer grading, receipt and learner-model updates — seven distinct Gemma 4 jobs, all schema-constrained JSON (the function-calling pattern). There is no non-model code path that "is" the app; the model is the engine.
3. **Open weights are the ethics.** A screen-and-camera watcher on a closed API would be surveillance — frames of a student's private life shipped to a third party with no alternative. Because Gemma's weights are open, there *is* an alternative: `heiddoon watch` runs the whole loop against Ollama on the student's own machine, frames judged and **discarded**, verdicts only, working with Wi-Fi off. We enforce this structurally rather than promising it — there is no column in our schema that can hold a frame, and the app's privacy banner is generated from the live configuration, so a hosted backend physically cannot render the local-only claim. This property is not a feature of our code; it is a property of Gemma being open.
4. **Honest note on where we ran it today.** Our development laptop has no CUDA. Measured: the E4B tag crashes on every call on Intel Arc (a GGML scheduler assertion), and 12B needs **77 seconds per vision call** on CPU — against a 20-second check-in cadence. So the numbers below were produced through a hosted Gemma endpoint, and the local path is verified working but not what we demoed. Rather than hide that, we built one provider seam with both backends behind it; the same code, the same prompts, and the same eval run either way. Roadmap, labelled as such: E2B on-device via AI Edge puts the same family in the student's pocket.

### Architecture

One codebase, four signals, two places the weights can run. The `heiddoon` package holds the five mechanics — contract compiler, frame verdict, work-diff, Bouncer, receipt — and a `Session` object that makes them a loop rather than five demos. Everything that happens goes through that one object, so the event log is an account of what actually occurred, and the receipt is generated from it rather than from a plausible story about it. The **web app** and the **local watcher** are two front ends over that same `Session` and the same SQLite database; they can run simultaneously, with the UI streaming the watcher's verdicts live. Signals: screen and camera frames (one vision call each), the contracted file's delta (one text call), and input-idle plus screen-stillness (no model call at all — spending inference to conclude "the screen didn't change" would be absurd). A single provider seam decides where Gemma runs; nothing above it knows the difference.

### Does it work

On our labelled frame set, Heid Doon scored **[FILL — the QUOTABLE NUMBER line from `python -m heiddoon eval`]**, including **[FILL]** of the hard cases that defeat any title-based blocker, at a median **[FILL]s** per verdict. Of the errors, **[FILL]** were false accusations (we flagged drift while the student was working) and **[FILL]** were missed drift — a distinction we report separately because they are not equally costly: a wrong nudge teaches the student to distrust the app, and a distrusted app gets uninstalled. The work-diff separated a genuine revision delta from a padding delta and a stalled file [FILL — confirm all three].

Three things our harness does that we'd want a judge to check, because each is a way a demo number quietly becomes a lie. It **refuses to write a results file at all** when the provider is our mock. It scores **synthetic mock-ups separately from real captures** and keeps them out of the headline number — a rendered mock-up of a video page is read by the model as text, so it proves the pipeline runs and nothing about screen understanding. And it **counts frames that didn't run**, so a flattering `6/6` cannot hide twelve cases that never executed. Every result carries the prompt version that produced it.

We also fixed the reliability problem underneath the number rather than around it: word counts are computed in Python and override the model's guess, a "progress" verdict on a file that shrank is overridden, and every schema repair is recorded so we can report JSON reliability ([FILL]% clean) instead of hiding retries.

### Challenges in a 7-hour sprint

Our own eval was the first thing that had to be fixed. The test set we started with was rendered mock-ups, and a mock-up of a video page is read by a vision model as *text* — it scores near-perfectly and measures nothing, so the first honest number was lower than the dishonest one available to us. Local inference then turned out to be unavailable on our hardware: the E4B tag crashes on Intel Arc with a scheduler assertion, and 12B needs 77 seconds per vision call on CPU, which is why the provider seam exists at all. The remaining time went on the things that make the loop real rather than demonstrable — persistence, so the learner model survives the process; the artifact watcher, so the work-diff is a live signal and not two pasted blobs; and enforcing tone in code, because asking a model not to shame someone is a request, not a rule. [FILL — cut to 3–4 sentences, keep what's true for you.]

### Honest limits & what we didn't ship

The learner model does persist across sessions — it is in SQLite, and it merges conservatively so a session where a topic never came up does not erase what we knew about it. What we cannot claim is that the *adaptation* is validated: we have hours of data, not weeks, so whether tomorrow's plan actually reduces drift is untested. Nudge-style adaptation and Gemma 4 audio check-ins (spoken 20-second recall, graded) are designed, not shipped. Idle detection is Windows-only so far; elsewhere it assumes the student is present, which is the safe direction. Screen *perception* has prior art (Rewind, Screenpipe); our contribution is the behavioural loop for learners — contract, negotiation, autopsy, adaptation — which does not. And the diff can be gamed by typing filler into your own notes — at which point Gemma flags padding, and you are, at minimum, typing about thermodynamics.

### What's next

Cross-session learner models; the E2B phone companion (same open weights, same privacy, in your pocket); a campus pilot — the venue for this hackathon is full of exactly the students this is for.

---
*Attachments: 💻 code repository — `pip install -e .` then `python -m heiddoon doctor` · 📊 labelled test set with `labels.json` · 🔗 the app: `python -m heiddoon serve` · ✅ `python -m heiddoon eval` reproduces every number above, and `pytest` runs 42 tests with no network, model or GPU required.*
