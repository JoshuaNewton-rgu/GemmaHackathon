# HEID DOON — Design Doc v1.0
**Build with Gemma: GDGoC Aberdeen · 26 July 2026 · submissions 17:00**
*This is the definitive spec. If a feature isn't in here, it doesn't get built today.*

---

## 1 · The concept

**One-liner:** A study companion that catches you procrastinating the moment it happens — and reads your real progress from the work itself.

**Position statement:** For students who procrastinate (nearly all of them), **Heid Doon** is a session companion that watches *with* you — semantically judging your screen, your presence, and your actual output against rules **you** wrote — unlike Q&A study tools (easy to ignore) and site blockers (easy to fool, dumb about context), because Gemma 4's open weights let a multimodal model do this **privately, on your own machine**.

**Tagline:** *It reads your work, not just your screen.*
**The knife line:** *You can hide a phone from a camera. You can't hide an empty page.*

**What it is NOT (say these out loud when scoping):**
- ❌ Not a chatbot tutor — it intervenes; answering questions is incidental
- ❌ Not a site blocker — verdicts are semantic (YouTube *lecture* passes; YouTube cats don't)
- ❌ Not surveillance — the student authors the rules, frames are judged locally and discarded, only verdicts persist

**Three design principles (every feature must satisfy all three):**
1. **Autonomy** — the student writes the contract; the app enforces *their* rules, never ours
2. **Compassion** — procrastination is emotion regulation failure, not laziness; no shame mechanics, self-forgiving restarts
3. **Truth** — progress is measured from the artifact (the work), not from surveilled activity

---

## 2 · The user loop (one session)

```
CONTRACT ──► WATCH ──► INTERVENE ──► NEGOTIATE ──► CHECKPOINT ──► RECEIPT ──► ADAPT
 "my rules"   3 signals   kind nudge     Bouncer:      retrieval      autopsy +   tomorrow's
  + artifacts  judged      at the        earn break     question       focus       contract,
  + why        locally     moment of     via retrieval  from YOUR      score +     hard stuff
               vs contract drift                        notes          learner Δ   before the
                                                                                   danger zone
```

---

## 3 · Feature spec × judging rubric

Rubric: **Gemma Integration 30 · Innovation & Impact 30 · Functionality 20 · Presentation & Writeup 20.**
Track entered: **Motivation & Habits** (behavioural design is our strongest suit); learner model still ships → Best Overall sees both tracks.

### The map (✓✓ = primary scorer, ✓ = supports)

| # | Feature | Gemma 30 | Innov 30 | Func 20 | Present 20 | Priority |
|---|---|---|---|---|---|---|
| F1 | **Contract compiler** — NL → structured rules JSON | ✓✓ function-calling pattern | ✓ autonomy design | ✓ | | **P0** |
| F2 | **Semantic screen verdicts** — frame + contract → on/off-task + reason + nudge | ✓✓ vision, model IS the feature | ✓✓ beats blockers | ✓✓ demo core | ✓ eval table | **P0** |
| F3 | **The eval** — 15-frame labelled test set, accuracy printed in-notebook | ✓✓ proof model works | ✓ | ✓✓ "does it work" | ✓✓ THE number | **P0** |
| F4 | **Semantic work-diff** — snapshot deltas judged: progress/padding/stalled | ✓✓ long-context judgment | ✓✓ the phone answer; device-independent | ✓ | ✓ | **P0** |
| F5 | **The Bouncer** — break earned via retrieval Q from own notes, graded | ✓ gen + structured grading | ✓✓ negotiation > blocking; retrieval practice | ✓ | | **P0** |
| F6 | **Receipt + drift autopsy + learner model Δ** | ✓✓ event-log → JSON update | ✓✓ avoidance profiling (novel) | ✓ | ✓ closes demo | **P0** |
| F7 | **Gradio app** (webcam + upload + diff + bouncer tabs, share link) | | | ✓✓ live demo | ✓ | **P0** |
| F8 | **Camera presence / phone-in-hand** — webcam frames, same pipeline | ✓✓ 2nd modality, same weights | ✓✓ kills the phone objection live | ✓ | | **P1** |
| F9 | **Local watcher** (`watcher.py`, Ollama E4B, frames discarded) | ✓✓ open-weights = the ethics | ✓✓ privacy-preserving watching | ✓ pitch beat | ✓ | **P1** (ships in repo regardless; live if laptop allows) |
| F10 | **Idle inference** — screen hash + input idle ⇒ "you're elsewhere" | ✓ cheap signal, Gemma decides response | ✓ | ✓ | | **P1** (an `if` statement) |
| F11 | Nudge-style adaptation (which tone gets *you* back fastest) | ✓ | ✓ | | | **P2 — writeup roadmap** |
| F12 | Voice check-ins (Gemma 4 audio input: 20-s spoken recall, graded) | ✓ 3rd modality | ✓ | | | **P2 — writeup roadmap** |
| F13 | Phone companion (Gemma 4 E2B on-device via AI Edge) | ✓ family story | ✓ | | | **P2 — writeup roadmap** |

**P0 = submission is broken without it. P1 = build if on schedule (F8 first). P2 = one honest sentence in the writeup: "designed, not shipped in 7 hours."**

### How each criterion gets banked

**Gemma Integration (30) — target 26+.** The argument is *necessity*, not usage: (a) verdicts are semantic — a title-blocker scores 0 on our hard eval cases, only a multimodal model passes lecture-vs-cats; (b) **every mechanic is a Gemma structured-output call** (contract, verdict, diff, quiz, grade, receipt) — remove the model and there is no product; (c) the **open-weights property is load-bearing**: screen/camera watching is only ethically shippable local, which closed cloud models cannot offer; (d) size ladder used as architecture — E4B where privacy/latency live (laptop + notebook default), 12B coach behind a flag. Evidence: every notebook cell is a live Gemma call; eval table printed by Run All.

**Innovation & Impact (30) — target 25+.** Brief-fit is 1:1 — "nudging at the right moment" = F2/F8, "adapting to how they're progressing" = F4/F6, "holding them accountable to their own goals" = F1/F5. Novelty: progress-from-artifact accountability (F4) and drift-autopsy avoidance profiling (F6) don't exist in mainstream tools; screen perception exists (Rewind/Screenpipe — we own this in the writeup) but the behavioural loop for learners doesn't. Impact grounding: procrastination affects the large majority of students (Steel's research programme); design follows the emotion-regulation literature — self-forgiveness after lapses reduces future procrastination (Wohl et al.), implementation intentions (contract), retrieval practice (Bouncer/checkpoints), autonomy-supportive framing (SDT) rather than surveillance-guilt.

**Functionality (20) — target 17+.** One loop, demoed end-to-end in <90s from the Gradio app, reproducible by judges via Run All with the bundled test set. Scope discipline per the kill-ladder below; canned fallback frames if webcam misbehaves.

**Presentation & Writeup (20) — target 17+.** ≤1,500 words, headings mirror the rubric verbatim, one architecture diagram, the eval number quoted exactly as printed, an honest "sprint challenges + not-shipped" section (judges reward honesty in a 1-day format), demo failure ladder.

---

## 4 · Architecture

```
┌── Student's laptop (private) ────────────┐   ┌── Kaggle Notebook (public brain+demo) ──┐
│ watcher.py — Ollama · Gemma 4 E4B        │   │ Gemma 4 E4B via transformers (GPU)      │
│  • screen frames (mss)                   │   │  • contract compiler                    │
│  • camera frames (cv2): phone-in-hand    │   │  • verdict fn + 15-frame EVAL           │
│  • idle inference (hash+input)           │   │  • work-diff · bouncer · receipt        │
│  frames judged → DISCARDED, verdicts only│   │  • Gradio app (webcam/upload) share URL │
└────────────── events JSON ───────────────┘   │  • %%writefile watcher.py (repo unity)  │
                                               └─────────────────────────────────────────┘
```
- **Submission** = Kaggle Writeup + this notebook (public; is the repo AND the demo) + Gradio share URL
- **Pitch** = live watcher on laptop if Ollama performs; else Gradio webcam tab (still live perception); else demo-mode prototype HTML; else recording

### Data contracts (all produced by Gemma structured-output calls)
```json
CONTRACT  {"task","allowed":[],"blocked":[],"artifacts":[],"signals":[],"tone","ends"}
VERDICT   {"frame_kind":"screen|camera","on_task":bool,"seen","reason","nudge"}
DIFF      {"delta_words":int,"substantive":bool,"summary","quality_note","verdict":"progress|padding|stalled"}
QUIZ      {"question","key_points":[]} → GRADE {"pass":bool,"feedback"}
RECEIPT   {"autopsy","learner_model":{...},"tomorrow","focus_score":int}
LEARNER   {"weak_topics":[],"strong_topics":[],"drift_patterns":[],"avg_focus_streak_min":int,
           "best_nudge_style","next_difficulty":"easier|same|harder"}
```

---

## 5 · Behavioural design rationale (for the writeup's Impact section)

| Mechanic | Research hook | Why it beats the default |
|---|---|---|
| Contract with "why it matters" | Implementation intentions (Gollwitzer) | Nudges quote *your own words* back — motivation from identity, not guilt |
| Kind nudges, no shame, no exclamation marks | Procrastination = emotion regulation (Pychyl, Sirois) | Shame fuels the avoidance cycle; warmth breaks it |
| Self-forgiving restart after drift | Self-forgiveness reduces future procrastination (Wohl et al.) | The streak resumes — lapse ≠ relapse |
| Bouncer: breaks earned via retrieval | Retrieval practice (Roediger & Karpicke) | The "cost" of a break is literally learning |
| Scheduled break before the danger zone | Drift autopsy data | You never have to *steal* a break — removes the trigger |
| Student-authored rules | Self-determination theory (autonomy) | Monitoring you opted into ≠ surveillance imposed on you |

---

## 6 · Scope ladder (from ~13:45, lock 17:00)

| By | Milestone | Kill rule |
|---|---|---|
| 14:30 | F2 verdict fn returns clean JSON on 3 real frames; test-set dataset uploaded | If model load fights you >20 min → smaller variant, no debugging heroics |
| 14:50 | F3 eval cell prints X/15 | If <10/15 → fix the prompt, not the model; hard cases can move to "known limits" |
| 15:10 | F4 diff + F5 bouncer working | Bouncer grading flaky → pass/fail on key-point overlap, still Gemma-generated |
| 15:30 | F6 receipt + F7 Gradio share link live · **insurance Save Version** | Gradio blocked → notebook IS the demo (allowed) — say so in writeup |
| 15:50 | F8 camera frames in Gradio webcam tab (P1) | Behind schedule → cut F8 live, keep one labelled camera frame in eval set |
| 16:10 | **Final Save Version started** · writeup text frozen | |
| 16:40 | **SUBMITTED** (track: Motivation & Habits) | Never trade submit-margin for a feature |

## 7 · Risks & honest-claims policy
- **Never claim "fully local" for the notebook path** — the claim is: *architecture is local-first; watcher.py runs local; notebook hosts the same open weights for judges' reproducibility*
- **Gaming the diff** ("what if they type filler?") → semantic padding detection + "fooling your own study app costs more than studying" — in writeup FAQ
- **False-positive nudges** (YouTube lecture case) → that's exactly what the eval's hard cases measure; quote the number, admit the misses
- **Prior art** (Rewind, Screenpipe) → named in writeup; our claim is the loop, not the perception
- **Latency** → 20-s cadence is a design choice (rhythm of check-ins, not millisecond policing) *and* an honest E4B budget

## 8 · Success criteria for today
1. Eval ≥ **13/15** printed by Run All
2. Gradio demo: contract → frame verdict → diff → receipt in **<90 s**
3. Notebook public, Run-All clean, watcher.py inside it
4. Writeup ≤1,500 words, submitted by **16:40**, headings = rubric
5. Pitch lands the two lines: *"reads your work, not just your screen"* · *"can't hide an empty page"*
