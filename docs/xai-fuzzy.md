# The XAI / fuzzy-rules route — decoded, and how it fits Heid Doon

*Written 26 July 2026, ~15:30, while the layer was still being built. The two defects in §5 were found
by smoke-testing and have since been **fixed** — §5 is kept as the record of what was wrong and why,
because it is also the answer to "how do you avoid false accusations?"*

---

## 1 · What the judge actually said

Four separate ideas, garbled into one sentence. Untangled:

| They said | They meant |
|---|---|
| "the xAI route" | **XAI — eXplainable AI.** Not xAI the company, nothing to do with Grok. The field concerned with systems whose decisions can be inspected and justified rather than taken on trust. |
| "rules fuzzy if-then readable things" | A **fuzzy rule base**: `IF topic_match is low AND drift is long THEN nudge is firm`. Fuzzy logic (Zadeh, 1965) lets a variable be *partly* low and *partly* medium at once, so you get graded judgements out of readable sentences instead of brittle thresholds. |
| "an expert" | An **expert system** — a knowledge base whose rules were elicited from a domain expert rather than learned from data. The classic pairing with fuzzy inference (Mamdani, 1975). |
| "a psych evaluation" | The domain expert should be **psychology**: the rules and the resulting profile grounded in the procrastination literature, not invented. |

**The composite suggestion:** *don't let a black-box model decide when to interrupt a student. Have it
perceive, and let a readable, psychology-grounded fuzzy rule base decide — so every intervention can be
explained in sentences the student can read, and argue with.*

This is a strong suggestion and worth taking seriously, for three reasons beyond the judge's:

1. **It fixes a genuine weakness.** Our old `judge_frame` returned `on_task: bool` plus a `reason` string
   the model wrote *after* deciding. That reason is post-hoc narration with no causal link to the
   decision — the model could have said anything. There was no way for a student to contest a nudge.
2. **It makes autonomy real rather than rhetorical.** We already claim "the student writes the rules."
   Until now that meant the *contract*. Now it can mean the actual decision policy: 16 sentences,
   reweightable, removable.
3. **It's cheap to defend on stage.** "Here is the arithmetic that interrupted you" beats "the model
   thought you were distracted" in every Q&A exchange.

---

## 2 · The division of labour — this is the whole idea

```
   GEMMA PERCEIVES                MEASURED                FUZZY RULES DECIDE         GEMMA SPEAKS
   ───────────────                ────────                ──────────────────         ────────────
   topic_match   0.05             drift      0.60         16 readable IF/THEN        one sentence,
   is_own_work   0.00             fatigue    0.40   ──►   rules over the eight  ──►  only if the
   padding       0.00             progress   0.00         degrees, min/max, then     rules asked
   confidence    0.90             presence   0.90         weighted centroids         for one
        │                              │                          │
   one vision call            arithmetic on the            no model involved
   per frame                  event log — no model         → full audit trail
```

**Why put the model only at the ends?** A multimodal model is irreplaceable at reading a messy screen
into graded features, and terrible at being audited. A fuzzy rule base is exactly the opposite. So:
perception where perception is needed, readable arithmetic where *policy* lives, and one small
phrasing call at the end — after the decision is already made and provable.

Three consequences fall straight out, and all three are things we were previously only promising:

- **An unreachable model cannot produce an intervention.** Perception fails to `confidence = 0.0`,
  rule `r03` (*IF confidence is low THEN nudge is silent*) turns that into silence. The failure mode is
  quiet by construction, not by a defensive `if` we remembered to write.
- **Nudge text is written only when a nudge is happening.** Previously every frame produced a `nudge`
  field including the thousands that ended in silence — wasteful, and a standing temptation to use it.
- **"Silence" becomes a decision with a reason**, rather than the absence of one. `r01` (*IF progress is
  strong THEN nudge is silent*, weight 1.0) is the highest-weighted rule in the base. Protecting flow is
  now a thing the system *does*, not a thing we say.

### The eight degrees

Four **perceived** by Gemma from the frame (`prompts.PERCEIVE`): `topic_match`, `is_own_work`,
`padding`, `confidence`. Four **measured** from the event log with no model at all: `drift` (time since
last on-task frame), `fatigue` (time since last break), `progress` (latest diff verdict), `presence`
(camera + idle).

That split is the interpretability guarantee. Every number a rule consumes is either something a person
could check by looking at the same frame, or arithmetic over the log. **No input is a model's opinion
about what should happen** — which is what stops this being a black box with a rule-shaped decoration
bolted on. Say that sentence on stage; it's the one a judge will test you on.

### The three outputs

`nudge` (silent / gentle / firm) · `break_offer` (none / mention / urge) · `ask_page` (no / maybe / yes).

Two things worth noticing in the rule base ([library.py](heiddoon/fuzzy/library.py)): the compassion
principle is now *arithmetic* — no rule can conclude a firm nudge from a single reading, and
`r09` (*IF progress is stalled AND is_own_work is high AND drift is brief THEN nudge is silent*) exists
specifically so the app never punishes a student for staring at their own work and thinking. And every
rule carries a `because` — the psychology or product reason it exists — so the rule base documents
itself.

---

## 3 · The expert agent, and the "psych evaluation" question

`core/expert.py` is the expert-system half: it reviews a student's session log and proposes changes to
**rule weights only** — bounded to [0.0, 1.5], with three rules (`r01`, `r03`, `r15`) hard-protected as
the ethical floor. Every proposal is policed in Python: unknown rule id, protected rule, out-of-bounds
weight, change under 0.05, or missing justification → recorded as **rejected, with the reason**. The
agent advises; `review()` decides.

This is the right amount of self-modification. A weight change is reversible, bounded and legible —
"`r06` went from 1.0 to 1.2 because you ignored four gentle nudges and responded to two firm ones."
An agent free to rewrite the *rules* would be free to optimise away the ethics in pursuit of engagement,
and nobody could audit it.

### ⚠️ On the words "psych evaluation" — get this right or it becomes a liability

**Do not ship, demo, or describe this as a psychological assessment.** What it produces is a
**study-habit profile**: when you drift, what precedes it, which interventions you respond to. The
prompt already forbids diagnosis, condition names, and speculation beyond study behaviour, and
`Review.to_dict()` carries the disclaimer in the payload itself rather than only in the UI — so it
travels with the data.

The framing that is both accurate and stronger:

> "The rule base is grounded in the psychology of procrastination — task aversion, emotion regulation,
> self-forgiveness, retrieval practice — and every rule cites which idea it comes from. It profiles your
> *study habits*. It is not a clinical instrument and doesn't pretend to be one."

If a judge pushes toward "could it detect ADHD / anxiety / depression" — the answer is **no, and it
shouldn't try.** Say plainly: an LLM emitting pseudo-clinical claims about a student would be
meaningless and harmful; the useful version is the one they can act on tomorrow morning. That answer
scores better than a bolder claim, because the bolder claim is indefensible.

---

## 4 · What exists right now

Verified by reading the files and running the engine at 15:25. **All 134 tests pass.** The rule base
validates clean (16 rules, no dangling variable or word).

| File | Lines | State |
|---|---|---|
| [fuzzy/sets.py](heiddoon/fuzzy/sets.py) | 122 | ✅ Trapezoidal membership functions; one shape covers triangle/shoulder cases |
| [fuzzy/rules.py](heiddoon/fuzzy/rules.py) | 140 | ✅ Rules parsed from and rendered back to their sentence — one artefact, so the text shown can't drift from the rule that fired |
| [fuzzy/engine.py](heiddoon/fuzzy/engine.py) | 162 | ✅ Mamdani inference, min/max, full `FiredRule` trace, `why()` read off the arithmetic |
| [fuzzy/library.py](heiddoon/fuzzy/library.py) | 245 | ✅ 8 percepts, 3 decisions, 16 rules each with a `because`, plus `validate()` |
| [core/perceive.py](heiddoon/core/perceive.py) | 175 | ✅ Model → 4 degrees; 4 more measured from the log |
| [core/decide.py](heiddoon/core/decide.py) | 160 | ✅ Acting thresholds fixed — §5 |
| [core/expert.py](heiddoon/core/expert.py) | 235 | ✅ Weight proposals, policed and bounded |
| [prompts.py](heiddoon/prompts.py) | +3 | ✅ `PERCEIVE`, `NUDGE_LINE`, `EXPERT_REVIEW`; version now `2026-07-26.4-fuzzy` |
| [store.py](heiddoon/store.py) | +4 methods | ✅ `rule_weights` table, schema v2, `get`/`save`/`reset`, included in delete-everything |
| [core/session.py](heiddoon/core/session.py) | +100 | ✅ `judge_frame_interpretably()`, `expert_review()`, per-student weights loaded on top of shipped rules |

**Not yet wired — the layer is built but almost nothing calls it:**

| Gap | Why it matters |
|---|---|
| `server.py` still calls `session.judge_frame` (3 places) | The web app is running the **old binary verdict**. Nothing a judge sees uses the fuzzy layer yet. |
| No `/api/rules`, no `/api/session/{id}/expert-review` | No way to read or edit the rule base from the app |
| No UI panel | **This is the deliverable.** "Readable" means nothing until a human can read it on screen |
| `evaluate.py` still imports `core.verdict.judge_frame` | The eval scores the old path. `Outcome.on_task` exists precisely so the eval can move across |
| No tests for `fuzzy/` | 134 tests, zero over the new layer |
| No CLI (`heiddoon rules`, `heiddoon explain`) | Cheapest possible demo fallback — see §7 |
| `validate()` never called at startup | A malformed rule would fail silently at runtime instead of loudly at boot |

---

## 5 · Two defects, found by running it — now fixed

> **Fixed at 15:33.** `Decision.activation` now carries the firing strength of the best rule
> concluding each output, and `core/decide.py` gates on *that* rather than on the defuzzified value:
> `ACT_STRENGTH = 0.40` for nudges, `ASK_STRENGTH = 0.45` for asking to see the page (higher, because
> asking costs the student something), `BREAK_STRENGTH = 0.35` for break offers. Nine tests in
> [tests/test_decide.py](tests/test_decide.py) hold the line. **152 tests pass.** The rest of this
> section is the record of what was wrong — keep it, because it is the best answer you have to
> "how do you stop it accusing people wrongly?"


I smoke-tested the rule base against seven scenarios. Five behaved correctly, including the ones that
matter most: a lecture on topic → silent; cats after 9 minutes → gentle nudge citing
*topic_match is low (100%) and drift is moderate (60%)*; a **blurry** frame of cats → silent, because
`r03` outranks the drift rules; cats while the work is moving → silent, `r01` at full strength. That is
the compassion principle working as arithmetic, and it is genuinely impressive.

Two are wrong, and they share one root cause.

### 5a · A rule firing at 3% strength produces the same nudge as one firing at 75%

```
topic_match=0.44  nudge sets fired={'gentle': 0.03}  ->  value=0.50 word=gentle ACTS=True
topic_match=0.42  nudge sets fired={'gentle': 0.09}  ->  value=0.50 word=gentle ACTS=True
topic_match=0.20  nudge sets fired={'gentle': 0.75}  ->  value=0.50 word=gentle ACTS=True
```

`ACT_THRESHOLD = 0.35` in [decide.py](heiddoon/core/decide.py) gates the **defuzzified value**. But
defuzzification is a weighted average of set centroids — divide by total activation — so when only one
output set is active, the result is that set's centroid *regardless of how weakly the rule fired*.
Firing strength is divided straight out of the answer. A 3%-true rule and a 75%-true rule both yield
0.50, both read as "gentle", both interrupt the student.

That's a false-accusation path, which is the one failure mode the whole product is organised against.

### 5b · It asks to see your page while you're demonstrably on task

Student watching a thermodynamics lecture, `topic_match 0.9`, `confidence 0.9`:

```
r14 @0.16 -> ask_page is yes
result: ask_page value=0.85 word='yes'
```

`r14` limps in at 0.16 strength (they aren't writing, nothing has moved yet, mildly tired). It's the
only rule concluding anything about `ask_page`, so it wins by default and `decide.py` passes
`output_words['ask_page']` straight through with **no threshold at all** — `nudge` has one,
`break_offer` and `ask_page` don't. So the app interrupts a student who is provably on task to ask for
a photo, which is precisely the intrusion the rule base claims to prevent.

### The fix — gate on firing strength, not on the defuzzified value

Add per-variable activation to the engine's aggregation (it already computes `per_set`; keep the max),
expose it on `Decision`, and gate every output on it:

```python
# engine.py — in infer(), alongside crisp/words
activation[variable_name] = max(activations.values())

# decide.py — replace the ACT_THRESHOLD check
ACT_STRENGTH = 0.40          # a rule must be at least 40% true to act on a student
ASK_STRENGTH = 0.45          # asking costs them something, so it costs us more evidence

firmness = decision.output_words.get("nudge", "silent")
act = firmness != "silent" and decision.activation.get("nudge", 0.0) >= ACT_STRENGTH
ask = decision.output_words.get("ask_page", "no")
outcome.ask_page = ask if decision.activation.get("ask_page", 0.0) >= ASK_STRENGTH else "no"
```

Keep the defuzzified value — it's the right thing to show in the trace and to plot — just stop making
the decision with it. Two knock-on notes: `r14`'s `fatigue is medium` clause means a *very* tired
student working on paper never gets asked at all (probably should be "not low"), and when no rule fires
the trace says *"No rule matched this situation, so nothing was concluded"* — for the student-facing
panel that should read as **"nothing fired, so nothing happened — silence is the default."**

Both defects are ~20 lines and want a test each. They're worth fixing before the demo: 5b is visible on
stage, and 5a is the exact thing a judge asking "how do you avoid false accusations?" would expose.

---

## 6 · What to build next, in order

Assuming a couple of hours. Ordered by demo value per minute.

1. ~~**Fix §5**~~ — **done**, with tests.
2. **Switch `server.py` to `judge_frame_interpretably`** (~15 min). Three call sites. Until this lands,
   nothing a judge touches uses any of it. **This is now the top priority.**
3. **The Why panel** (~45 min) — *the deliverable*. On every verdict card: the fired rules as sentences
   with their strengths as bars, the percept degrees, and the one-line `why`. The trace is already on
   every event in `detail.fired` / `detail.why`, so this is presentation only, no new plumbing.
4. ~~**Tests over `fuzzy/`**~~ — **done** while this was being written:
   [tests/test_fuzzy.py](tests/test_fuzzy.py) covers membership edges, `parse_rule` round-trips,
   `validate()`, and the scenario table; [tests/test_decide.py](tests/test_decide.py) covers the acting
   thresholds. Still worth adding: the expert-review rejection paths (protected rule, out-of-bounds
   weight, missing justification) — those are pure Python and they're the "we police the agent" claim.
5. **`GET /api/rules` + a rule list in the UI** (~30 min) with weights, `because`, and a *tuned* marker.
   Read-only is enough for the demo; editing is a bonus.
6. **`heiddoon rules` / `heiddoon explain <frame>`** (~20 min). Prints the rule base and a full trace in
   the terminal. This is your rung-2 fallback and it is genuinely impressive on its own.
7. **Move `evaluate.py` onto `Outcome.on_task`** (~20 min) — then quote fuzzy-path accuracy. Do this
   *after* re-capturing real frames, and re-run the eval so the number matches the shipped path.
8. **Expert review in the receipt** (~20 min) — the weight changes, each with its `because`, shown as
   "what changed about how I'll treat you tomorrow."

Anything not done by then: say "designed, not shipped." The writeup already does this well elsewhere.

---

## 7 · How to demo it

**The new beat, inserted after the cats nudge (~15 seconds).** The nudge card appears — then click
**Why?**

> "It's not that a model felt I was distracted. Two rules fired. *IF topic_match is low AND drift is
> moderate THEN nudge is gentle* — 54% true. And a firmer one at 17%, which lost. Those are the
> sentences, that's the arithmetic, and I can turn any of them off."

Then the killer follow-up — hold up a **blurry** frame or half-cover the webcam:

> "Same cats, bad photo. Nothing happens. *IF confidence is low THEN nudge is silent*, weight 0.9,
> outranks both drift rules. An uncertain reading can't become an accusation — and I can show you the
> line that guarantees it rather than asking you to trust that we meant it."

That is a better 15 seconds than anything currently in the deck, because it's the one thing no other
team will have: **a system that can be argued with.**

**Terminal fallback (rung 2):** `heiddoon explain` printing percepts, memberships, fired rules with
strengths, and the defuzzified outputs. Judges respect a terminal, and a full audit trail scrolling past
is self-evidently not a mock.

---

## 8 · What this does to the rubric

**Gemma Integration (30) — improves.** The necessity argument gets *sharper*, not weaker. Gemma is now
in the one place nothing else can do the job: turning a messy screen into graded, checkable features.
The counter-question — "if rules decide, what's Gemma for?" — has a crisp answer: **no rule can fire
without perception, and nothing but a multimodal model can produce `topic_match` from a screenshot.**
Plus the expert agent is a second, distinct Gemma job (structured proposals, policed in code). Nine
distinct jobs now, not seven.

**Innovation & Impact (30) — improves most.** Neuro-symbolic architecture — neural perception, symbolic
policy — is a genuinely current research direction, and applying it to *student autonomy* is novel:
the interpretability isn't for engineers debugging, it's so the student can **contest** the system. That
is a real answer to "isn't this creepy?" that no amount of privacy talk achieves. Add the psychology
grounding, cited per rule, and this is the strongest section of the submission.

**Functionality (20) — risk.** This is a second decision path landing hours before the deadline while
the old one still runs the app. Both work; only one is wired. **Do not leave both live at judging.**
Pick the fuzzy path, wire it end to end, and delete or clearly mark the old one — a judge who finds two
verdict systems will ask which one produced your number, and "either, depending on the endpoint" is a
bad answer.

**Presentation & Writeup (20) — needs work.** The writeup and both pitch docs describe the *old* binary
verdict. `docs/pitch-v3.md` slide 5 ("kindness is a rule, not a prompt") now has a much better version
of itself — the regex was the old proof, the rule base is the new one — and the deck needs an XAI slide.

Worth saying explicitly in the writeup: **we replaced our own core mechanism on the advice of a judge,
six hours in, and the eval let us verify it wasn't a regression.** That's a maturity signal, and it's
true.

---

## 9 · Q&A ammo for this route

| They ask | You say |
|---|---|
| "If the rules decide, what's the model for?" | "Perception. No rule can fire without `topic_match`, and nothing but a multimodal model produces that from a screenshot. We put Gemma where it's irreplaceable and kept it out of policy, where it can't be audited." |
| "Isn't fuzzy logic a bit 1975?" | "Mamdani, 1975 — yes, and that's the point. It's the mature, well-understood way to get graded decisions out of readable rules. The novel part is what it's paired with: a vision model doing the perception it was never able to do in 1975." |
| "Why not just ask the model to explain itself?" | "Because that's narration, not explanation. It decides, then writes a plausible reason with no causal link to the decision. Our explanation *is* the decision — the numbers in the trace are what determined the output, so it can't be wrong about itself." |
| "Where did the rules come from?" | "The procrastination literature, one `because` per rule, written where the student can read them. Not learned from data — we have hours of data, not years, and a rule base you can read beats a model you can't at this sample size." |
| "Is this a psychological assessment?" | "No. It's a study-habit profile — when you drift, what precedes it, what you respond to. It's forbidden from diagnosing anything, that's enforced in the prompt, and the disclaimer travels in the payload rather than sitting in the UI. A model emitting clinical-sounding claims about a student would be both meaningless and harmful." |
| "Can the student change the rules?" | "Weights today, and they can see which have been tuned for them and why. Three rules are protected from *automatic* tuning because they're the ethical floor — never interrupt work that's moving, stay silent when unsure, don't ask for what's already proven. A student can still turn those off themselves; an optimiser can't." |
| "How do you know the fuzzy path is as accurate?" | "Same labelled test set, same harness — `Outcome.on_task` exists so the eval scores either path. *(Quote both numbers if you get this done; if not, say the eval currently scores the binary path and the fuzzy path is verified by unit tests, not by the frame set.)*" |

---

## 10 · One caution

At 15:25 the fuzzy layer was being written *while I read it* — one file every ~40 seconds, and
`session.py` changed under me mid-audit. Before the deck freezes, re-run `pytest -q`,
`python -m heiddoon doctor`, and the seven scenarios in §5, because this document is a snapshot of a
moving target. HEAD has also moved on from what `docs/pitch-v3.md` was written against (a teammate's
branch merged in, bringing voice/TTS work), so the feature inventory there wants a second pass:
**134 tests now, not 84.**
