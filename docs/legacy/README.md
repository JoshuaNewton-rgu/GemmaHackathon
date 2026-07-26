# Superseded

These are the artifacts from the pitch bundle, kept because they record how the
product was thought through before it was built. None of them run any more, and
none of them should be used as a reference for behaviour.

| File | Superseded by | Why |
|---|---|---|
| `kaggle-notebook.ipynb` | the `heiddoon` package | Mechanics lived in notebook cells that only ran on a Kaggle GPU, with a `MOCK = True` path that emitted canned verdicts indistinguishable from real ones once printed. |
| `prototype.html` | `heiddoon/web/` | A scripted demo — its `verdict()` was hardcoded and it made no model calls. Its design tokens live on in `heiddoon/web/app.css`. |
| `watcher-v1.py` | `heiddoon/watchers/` | Judged screen and camera frames but appended verdicts to an `events.jsonl` that nothing read, had no artifact diffing, no idle inference, and no session or receipt. |

The design doc, pitch and writeup draft in `docs/` are still live working documents.
