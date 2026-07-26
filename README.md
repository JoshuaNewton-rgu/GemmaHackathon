# Heid Doon

*A study companion that catches you procrastinating the moment it happens — and reads your real
progress from the work itself.*

**It reads your work, not just your screen.**
You can hide a phone from a camera. You can't hide an empty page.

---

## What it does

One session: **Contract → Watch → Intervene → Negotiate → Checkpoint → Receipt → Adapt.**

You write a contract in your own words — what you're studying, why it matters, what counts as
on-task for *you*, and which file you're working in. Then four signals feed one loop:

| Signal | Answers | Cost |
|---|---|---|
| **Screen** | What are you looking at, and does it mean what your contract allows? | one vision call |
| **Camera** | Are you here, and is there a phone in your hand? | one vision call |
| **Artifact** | Did the work actually move? | one text call |
| **Idle** | Are you at the machine at all? | free — no model |

Verdicts are **semantic**, not a blocklist: a lecture about your topic passes, entertainment on
the same site doesn't; the right module's PDF passes, the wrong module's doesn't. That distinction
is the entire reason a multimodal model is needed here, and it's what the eval measures.

The **artifact signal** is the one that matters most, because it's the only one that's
device-independent. Procrastinate on whatever device you like — twenty minutes of it shows up as
an empty diff.

Breaks are **negotiated, not blocked**: ask for one and you answer a single retrieval question
generated from your own notes. Sessions end with a **receipt** — a drift autopsy that names the
pattern and its trigger without shame, and an updated learner model that shapes tomorrow.

## Three principles, enforced in code

1. **Autonomy** — the contract compiler is instructed never to add a restriction you didn't ask
   for, and unknown signals are dropped rather than silently ignored.
2. **Compassion** — exclamation marks and shaming language are stripped from every nudge in
   [`core/verdict.py`](heiddoon/core/verdict.py) rather than merely discouraged in the prompt.
   When the model is unreachable, the verdict defaults to *on task*: a false accusation costs more
   trust than a missed drift.
3. **Truth** — word counts are computed in Python, not guessed by the model. A "progress" verdict
   on a file that shrank is overridden. The eval refuses to report a number it can't stand behind.

## Privacy

**There is no column anywhere in the schema that can hold a frame.** Screen and camera captures
exist as Python objects for the length of one judgment and are then dropped. What persists is the
verdict — what was seen, in words, and whether it was on task.

Snapshots of your *contracted file* are stored, because diffing needs a previous version. That's
your own file, on your own machine, in a SQLite database you can delete.

Whether frames leave the machine depends entirely on the backend:

| Backend | Frames leave the machine |
|---|---|
| `ollama` | **No.** Judged locally, works with Wi-Fi off. |
| `google` / `openai_compat` | **Yes** — sent to a hosted endpoint, then discarded. |

The app never claims otherwise: the privacy banner text is generated from the live configuration
in [`server.py`](heiddoon/server.py), so a hosted backend cannot render the local-only promise.

## Install

```bash
pip install -e ".[watch,web,dev]"      # watch = screen/camera, web = the app
cp .env.example .env                   # then put your key in it
```

## Check it works before debugging anything else

```bash
python -m heiddoon doctor
```

Prints your configuration, **the model handles your key can actually reach**, a text call, a
vision call with timings, and whether local capture is available. It also warns when one verdict
takes longer than the check-in cadence, which is the difference between a working watcher and one
that's permanently a minute behind.

## Use it

```bash
python -m heiddoon contract "I'm revising entropy until 12:30. Lectures and PDFs are fine, no
social media. Track notes_thermo.md. Camera on." --out contract.json

python -m heiddoon serve            # the web app on http://127.0.0.1:8000
python -m heiddoon watch            # the local watcher, against your real screen
python -m heiddoon eval             # score the labelled frame set
```

The web app and the watcher are two front ends over **the same `Session` object** and the same
database, so anything the UI shows has been through the same code path as anything the watcher
recorded. They can run at once — the UI streams the watcher's verdicts over SSE.

## The eval

```bash
python -m heiddoon eval --out eval_results.json
```

Three rules are enforced in code, because each is a way a demo number quietly becomes a lie:

- **Mock output is never written to a results file.** If the provider is the mock, the harness
  refuses.
- **Synthetic frames are scored separately from real ones.** A rendered mock-up of a video page is
  read by the model as text; it proves the pipeline runs and nothing about screen understanding.
  Only real captures appear in the headline number.
- **Frames that didn't run are counted.** A missing file is reported as not-run, so `6/6` can't
  hide the fact that twelve of eighteen cases never executed.

The report also separates **false accusations** from **missed drift** — they are not equally bad —
and records the prompt version, so a number can always be traced back to the wording that
produced it.

## Configuration

Everything is environment-driven; see [`.env.example`](.env.example).

| Variable | Default | |
|---|---|---|
| `HEIDDOON_PROVIDER` | `google` | `google`, `openai_compat`, `ollama`, `mock` |
| `HEIDDOON_MODEL` | per provider | run `doctor` to see valid handles |
| `GEMMA_API_KEY` | — | for the hosted backends |
| `HEIDDOON_OLLAMA_MODEL` | `gemma4:12b` | |
| `HEIDDOON_CADENCE_S` | `20` | seconds between check-ins |
| `HEIDDOON_DB` | `./heiddoon.db` | |

## Layout

```
heiddoon/
  providers/     where the weights run — hosted API, local Ollama, or a mock
  schemas.py     the data contracts; coerce rather than raise, and record repairs
  prompts.py     every prompt, version-stamped so eval numbers stay traceable
  core/          the five mechanics + the Session that makes them one loop
  watchers/      screen · camera · artifact · idle
  store.py       SQLite: verdicts and note snapshots, never frames
  evaluate.py    the eval, which refuses to report unquotable numbers
  server.py      HTTP over the same Session the watcher uses
  web/           the front end
tests/           42 tests, no network, no model, no GPU
```

## Known limits

- **Local inference is hardware-dependent.** On a machine without CUDA, one vision call can take
  over a minute — far longer than the 20-second cadence. `doctor` will tell you. `gemma4:e4b`
  crashes outright on Intel Arc with a GGML scheduler assertion; the error message says so and
  suggests the alternatives rather than looking like a bug in this code.
- **Idle detection is Windows-only** so far. Elsewhere it returns 0, which means "assume they're
  here" — the safe direction.
- **The diff can be gamed** by typing filler into your own notes. At which point the model flags
  padding, and you are, at minimum, typing about thermodynamics.
- Screen *perception* has prior art (Rewind, Screenpipe). The contribution here is the behavioural
  loop for learners, not the perception.
