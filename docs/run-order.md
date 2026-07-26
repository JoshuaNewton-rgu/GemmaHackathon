# RUN ORDER — from bundle to submitted (do these in sequence)

**You edit exactly two things in the notebook: `MODEL_ID` (cell 1) and nothing else unless it breaks.**

1. **Kaggle → Datasets → New Dataset** → upload the whole `testset/` folder → title `heid-doon-testset` → **make it public**. (2 min)
2. **Kaggle → Code → New Notebook → File → Import Notebook** → upload `heid-doon-kaggle-notebook.ipynb`. (1 min)
3. Notebook settings (right panel): **Accelerator = GPU** · **Internet = ON**. If Internet/GPU are greyed out, phone-verify your account NOW: Settings → Phone verification. (2 min)
4. **Add Input** → *Models* → search **Gemma 4** → attach the instruction-tuned E4B-class variant from the participant guide. Also **Add Input → Datasets → heid-doon-testset**. (2 min)
5. Run cell 1. It auto-detects the attached model; if it can't, paste the participant guide's handle into `MODEL_ID`. **Confirm it prints `✓ loaded` and `MOCK` is not triggered.** (5–10 min incl. download)
6. Run cells top-to-bottom through the eval. Six placeholder frames will score; `_TODO_*` slots are skipped with a printed reminder. (5 min)
7. **Replace the placeholders with real captures** (10 min, do it from your laptop):
   - screenshot your real notes/editor, a real distraction site, keep/replace my six mocks as you like
   - webcam photos: phone-in-hand, at-desk, empty chair (drop the `_TODO_` prefix in both filename and labels.json)
   - update the dataset (New Version) → re-run eval → **that printed number is your writeup number**
8. Run the Gradio cell → copy the **share URL** → test it on your phone. Keep this session running through judging.
9. **Writeup**: paste `writeup-draft.md` into your Kaggle Writeup, fill every `[FILL]`, select track **Motivation & Habits**, attach notebook + dataset + share URL under Project Links. **Click Submit now** (you can re-submit after edits — drafts don't count).
10. **15:30 — insurance Save Version** (Run All). Fix anything it surfaces.
11. **16:10 — final Save Version.** While it runs, polish the writeup. **16:40 — final Submit.** Hard stop.
12. Pitch prep (17:00–18:00): `watcher.py` live on your laptop if Ollama's ready (`ollama pull` the guide's tag NOW in the background); fallback = Gradio webcam tab; fallback = prototype HTML demo-mode; fallback = recording.

**Panic lines:**
- Model won't load → try the Kaggle Models path in Add Input (no HF token needed); wrong class errors → ask an organiser for the guide's exact snippet; worst case the notebook runs in MOCK mode so you can still wire UI — but NEVER submit mock numbers.
- Gradio share blocked → the notebook IS the demo (accepted format); say so in the writeup attachment line.
- Behind at 15:30 → design doc kill rules: cut camera live-demo, keep the labelled camera frames in the eval.
