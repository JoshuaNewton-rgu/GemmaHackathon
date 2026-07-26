# HEID DOON — The Pitch (2:00) · v2
*Doric stripped (the name stays — Scots for "head down", your one local touch). New beats: the phone answer + progress-from-the-work. Rehearse ×3.*

**Pre-stage checklist:** app running · two YouTube tabs pre-opened (thermo lecture + cat compilation) · your actual phone on the desk · a notes file with a visible diff ready · Ollama warm · hotspot on · prototype demo-mode in a spare tab · backup video on desktop.

---

## 0:00–0:15 — Hook
> "Every study tool in this room can answer questions. None of them are there at the moment that actually decides your grade — 11pm, deadline in nine hours, one new tab. **Heid Doon is.** And it doesn't just watch your screen — it reads your *work*."

## 0:15–0:35 — The Contract *(autonomy beat)*
> "A session starts with a contract, not a login: what I'm studying, why it matters to me, **my rules** — lectures allowed, docs allowed — and I point it at the file I'm working in. I wrote the rules. Heid Doon holds me to them."

*[Click **Heid doon →**]*

## 0:35–1:00 — The semantic moment *(Gemma-essential — never cut)*
> "I open YouTube." *[lecture tab]* "**Nothing happens.** It read the screen — a thermodynamics lecture — checked my contract, let it pass. A window-title blocker calls this procrastination. **Gemma 4 can see that it isn't.** Now—" *[cat tab; nudge fires]* "—same website, different meaning. Multimodal screen understanding judged against *my* goal, running **on this laptop** on Gemma 4 E4B. No cloud."

## 1:00–1:25 — The phone answer *(the objection every judge is holding — say it before they do)*
> "But nobody procrastinates on their laptop anymore, right? Watch." *[pick up your phone, look at it]* "…**'Phone in hand, eyes off screen 38 seconds.'** The same local model reads a camera frame. And if I hide the phone under the desk? Here's the deeper trick: Heid Doon snapshots my notes file and **Gemma semantically diffs it** — twenty minutes of phone shows up as an empty diff, padding shows up as padding, real work shows up as '+218 words, two worked problems.' **You can hide a phone from a camera. You can't hide an empty page.**"

## 1:25–1:40 — Emotion + negotiation
> "And it never shames you — procrastination is an emotion problem, not a laziness problem. Want a break? Negotiate: answer one retrieval question generated from your own notes and the Bouncer lets you out. Drift anyway? The restart is self-forgiving — that's what actually reduces the *next* episode."

## 1:40–1:52 — Receipt + why Gemma
> "Sessions end with a receipt: focus score, drift autopsy — I drift 25 minutes in, always after the derivations — and a learner model that schedules tomorrow's hardest material before my danger zone. **One open family doing five jobs**: screen vision, camera presence, semantic work diffs, retrieval quizzes, and the function calls driving every mechanic. E4B where privacy lives, 12B where reasoning lives. A closed cloud API doing this would be surveillance. **On your own machine, it's a study partner. That's why it's Gemma.**"

## 1:52–2:00 — Number + close
> "Fifteen-frame test set: **14 caught — including lecture-versus-cats and phone-in-hand.** Six hours. Screen-watching is a commodity; a behavioural loop that reads real progress is not. **Heid doon.**"

---

## Q&A ammo

| They ask | You say |
|---|---|
| "What if they use their phone?" | Answered in the demo — three layers: camera catches the glance; idle inference catches the absence (screen unchanged + no input = you're elsewhere); the work diff catches the truth. The diff is device-independent — it measures output, not activity. |
| "Window titles / a blocklist would do this" | Titles lie. Lecture-vs-cats is one site; a PDF can be the wrong module's PDF. Verdicts are semantic, against the declared task — that's a multimodal model's job. |
| "Isn't this creepy?" | User writes the rules; session-scoped; frames classified then **discarded** — verdicts only; all local. The cloud version *would* be creepy — that's precisely why open weights matter. |
| "Couldn't they just fake the notes file?" | You'd be typing filler into your own notes to fool your own study app — at that point you're… studying-adjacent. And the diff is *semantic*: Gemma flags padding vs substance. Gaming it costs more than working. |
| "Rewind / Screenpipe exist" | Screen perception is a commodity and we say so. The product is the loop: contract → verdict → negotiation → work-diff → autopsy → adapted plan. Nobody ships that for learners. |
| "Is it really local?" | Watcher: yes — `ollama ps` live. Coach runs 12B on Kaggle's free GPU — same open weights anyone can pull. *(Only claim what's true on the day.)* |
| "Phone companion?" | Roadmap, and it's cheap: Gemma 4 E2B runs on-device on Android via AI Edge — same family, same privacy, in your pocket. |

## Demo failure ladder
1. Live app → 2. Prototype demo-mode (▶ button — now includes the phone + work-diff beats after the nudge) → 3. Backup recording.

## The one number
15-frame test set before 15:30: 5 on-task (incl. YouTube lecture) · 5 off-task (incl. cats, **phone-in-hand camera frame**) · 5 hard (wrong-module PDF, Discord-with-classmates, notes-diff padding vs substance). Report X/15 honestly.

## Build deltas vs the original plan (~4h left — priority order)
1. **Artifact diff loop** (~45–60 min): watch the contract's file(s) by mtime; snapshot; 12B judges delta `{delta_words, substantive, summary}`. This is your Personalisation-track evidence AND the phone answer. Highest value per minute — build first.
2. **Camera presence** (~30–45 min, reuses screenshot pipeline): one `cv2.VideoCapture` frame alternated with screen frames → `{present, phone_in_hand}`. The live phone-pickup beat is worth it if the E4B latency budget allows; otherwise cut and keep idle-inference (free: screen hash + input idle time).
3. **Checkpoint retrieval quiz** — only if 1–2 land early; otherwise it lives in the writeup as designed-not-shipped (say so honestly).
