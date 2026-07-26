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
3. **Open weights are the ethics.** A screen-and-camera watcher built on a closed cloud API would be surveillance — frames of a student's private life shipped to a third party. Heid Doon's local watcher (`watcher.py`, in the repo, written by the notebook) runs Gemma 4 E4B on the student's own laptop via Ollama: frames are judged and **discarded**, verdicts only, works with Wi-Fi off. This privacy property is not a feature of our code — it is a property of Gemma being open. That is why this app can only exist on Gemma.
4. **The size ladder as architecture.** E4B where privacy and latency live (the laptop watcher; also the notebook default so judges can re-run everything quickly); the 12B coach tested behind a flag [FILL — keep only if true]. Roadmap, honestly labelled as such: E2B on-device via AI Edge puts the same family in the student's pocket; 256K context holds a whole course.

### Architecture

Two halves, one model family. The **Kaggle notebook** (public — it is simultaneously our code repository and our demo) hosts Gemma 4 on the free GPU and implements every mechanic cell-by-cell, then launches a Gradio app with real session state: verdicts, diffs and quiz results accumulate into an event log, and *End session* generates the receipt from what actually happened. The **local watcher** (`watcher.py` + `contract.json`, both written into the repo by the notebook) alternates screen and webcam frames every 20 seconds against Ollama — a deliberate rhythm of check-ins, not millisecond policing. Judges can reproduce every watcher verdict in the notebook on the same open weights, on our bundled, labelled test set, with one click of Run All.

### Does it work

On our 15-frame labelled test set — 5 on-task, 5 off-task, 5 hard cases (YouTube lecture, wrong-module PDF, on-topic chat, phone-in-hand webcam frame, padding text) — the watcher scored **[FILL — X/15 exactly as printed by the eval cell]**, including **[FILL — Y/5] of the hard cases** that defeat any title-based blocker, at a median **[FILL — Z]s** per verdict on the notebook GPU. The work-diff correctly separated a genuine revision delta (worked examples added) from a padding delta (filler prose) and a stalled file [FILL — confirm all three verdicts from cell 5]. The full loop — contract, verdict, diff, Bouncer, receipt — runs end-to-end in the Gradio app in under [FILL] seconds.

*(Numbers above are printed by the notebook's eval cell and saved to `eval_results.json`; quote them exactly, misses included.)*

### Challenges in a 7-hour sprint

[FILL — 3-4 honest sentences. Candidates, keep what's true: prompt iteration to stop false-positive nudges on the YouTube-lecture case; JSON reliability from a small model under time pressure (solved with schema-in-prompt + regex extraction + one retry); model-loading fights on Kaggle; deciding to measure progress from artifacts after realising screen-watching alone can't see a phone.]

### Honest limits & what we didn't ship

The learner model persists within a session, not yet across real days — streaks and cross-session adaptation are designed (schema shipped) but a one-day build demos minutes, not weeks. Nudge-style adaptation and Gemma 4 audio check-ins (spoken 20-second recall, graded) are designed, not shipped. Screen *perception* has prior art (Rewind, Screenpipe); our contribution is the behavioural loop for learners — contract, negotiation, autopsy, adaptation — which does not. And the diff can be gamed by typing filler into your own notes — at which point Gemma flags padding, and you are, at minimum, typing about thermodynamics.

### What's next

Cross-session learner models; the E2B phone companion (same open weights, same privacy, in your pocket); a campus pilot — the venue for this hackathon is full of exactly the students this is for.

---
*Attachments: 📓 notebook (public, Run-All reproducible — code repo + demo) · 📊 test-set dataset (public) · 🔗 live Gradio app: [FILL URL] — or Run All this notebook.*
