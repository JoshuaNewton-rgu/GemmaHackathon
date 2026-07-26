# ProofStudy (working name)

Jordan and Joshua — [Build with Gemma 4 (GDGoC Aberdeen Hackathon)](https://github.com/Konrad-Rejman/Build_With_Gemma_GDGoC_Aberdeen_Hackathon/blob/main/Using-Gemma-4-Participant-Guide.md) · [Kaggle competition](https://www.kaggle.com/competitions/build-with-gemma-gdg-aberdeen/overview)

A study companion that makes students actually learn instead of just sitting at the desk. Students run timed study blocks, photograph their handwritten notes as proof-of-work, and have to pass a short recall quiz *generated from their own notes* before a break is unlocked. Feedback comes from a Gemma-4-powered voice persona (Scottish Granny, Disappointed Mother, Angry Father).

## Why this stack

| Decision | Choice | Reasoning |
|---|---|---|
| Monorepo | npm workspaces (`backend`, `frontend`) | One repo, one `npm install`, no extra tooling needed for a hackathon-sized project. |
| Backend | Node.js + TypeScript + Express | Fast to iterate, huge ecosystem for OCR/AI SDKs, easy to deploy anywhere. |
| Database | MongoDB + Mongoose | Note text, OCR output, and quiz JSON are naturally document-shaped and evolve fast during a hackathon; schema flexibility beats relational rigidity here. |
| Frontend | Expo (React Native + React Native Web) | Camera-based note upload is core to the product — Expo gives native camera/notifications on iOS & Android *and* a web build from one codebase. |
| AI model | **Gemma 4** (`gemma-4-31b-it` / `gemma-4-26b-a4b-it`) | Required for the hackathon. Used for: quiz generation, persona coach messages, and handwriting OCR (Gemma 4 is multimodal — text + image in). |
| Model hosting | Swappable provider (`gemini_api` \| `self_hosted`) | Ship fast against the Gemini API today; drop in a self-hosted Ollama/vLLM endpoint later with zero code changes outside `backend/src/config/gemma.ts`. |
| TTS | Swappable provider (`device` \| `elevenlabs`) | Defaults to on-device TTS (Expo Speech / Web Speech API) so the app works offline with zero extra API keys; swap in a real voice-cloning provider (e.g. ElevenLabs) for distinct persona voices later. |

## Folder structure

```
proofstudy/ (repo: GemmaHackathon)
  frontend/                 Expo app (React Native + web)
    src/
      app/                  Navigation root
      modules/              Session, Break, Progress, Auth, Settings
      components/           Timer, UploadButton, Quiz, Avatar, AudioPlayer, Layout
      services/             httpClient, auth, speech (on-device TTS)
      types/                Shared API types
  backend/                  Express + TypeScript API
    src/
      config/               env, db, gemma (provider), ocr, tts
      modules/
        auth/                 register/login, JWT
        session/              start/pause/end study sessions
        notes/                image upload, OCR (via Gemma vision), progress score
        quiz/                 quiz generation + grading (session quiz & break quiz)
        coach/                persona message + TTS generation
        gamification/         XP, streaks, achievements
      middleware/            auth, upload (multer), error handler
      utils/                 scoring, logger, asyncHandler
  infra/
    docker-compose.yml       Local MongoDB
  package.json               npm workspaces root
```

## Data model (Mongoose)

- **User** — email, passwordHash, persona, level, xp, stats (focus/discipline/knowledge/consistency), streak
- **Session** — userId, subject, startedAt, endedAt, status, progressScore
- **NoteSnapshot** — sessionId, imageUrl, ocrText, keywords, wordCount
- **Quiz** — sessionId, kind (`session` \| `break`), questions[], correctCount, passed
- **CoachMessage** — userId, sessionId, type (`praise` \| `roast`), text, audioUrl/localTts flag

## Gemma 4 integration

All three AI-dependent features run through the same Gemma 4 client (`backend/src/config/gemma.ts`):

1. **Notes OCR + analysis** (`modules/notes/notes.service.ts`) — sends the note photo directly to Gemma 4's vision input, asking it to transcribe handwriting to text and extract keywords/headings in structured JSON (Gemma 4 supports native structured JSON output).
2. **Quiz generation** (`modules/quiz/quiz.service.ts`) — sends note text + difficulty level, gets back a strict JSON array of questions via Gemma 4 function-calling/JSON-schema output.
3. **Coach persona messages** (`modules/coach/coach.service.ts`) — sends the persona's style template + progress score, gets back a short in-character line of praise or a roast.

Switch providers with `GEMMA_PROVIDER` in `backend/.env`:

```
GEMMA_PROVIDER=gemini_api        # or self_hosted
GEMINI_API_KEY=...               # required for gemini_api
GEMMA_MODEL=gemma-4-31b-it       # or gemma-4-26b-a4b-it for lower latency
SELF_HOSTED_GEMMA_URL=http://localhost:11434  # required for self_hosted (Ollama/vLLM OpenAI-compatible endpoint)
```

## Getting started

```bash
# 1. install all workspace deps
npm install

# 2. start local MongoDB
npm run infra:up

# 3. configure env
cp backend/.env.example backend/.env   # fill in GEMINI_API_KEY etc. (or reuse the root .env you already have)
cp frontend/.env.example frontend/.env

# 4. run backend + frontend together
npm run dev
```

Backend runs on `http://localhost:4000`, Expo dev tools open for web/iOS/Android.

## Status

Early scaffold — routes, models, and AI provider interfaces are wired end-to-end with real Gemma 4 calls; OCR/quiz/coach prompts will need tuning during the hackathon, and only on-device TTS is implemented by default (persona voice API is stubbed behind the `tts` provider interface).
