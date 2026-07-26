"""Heid Doon — a study companion that reads your work, not just your screen.

Layout:
    providers/   where the weights run: hosted API, local Ollama, or a mock
    schemas.py   the data contracts every model call must return
    prompts.py   every prompt, version-stamped so eval numbers stay traceable
    core/        the five mechanics, plus the Session that makes them one loop
    watchers/    the signals: screen, camera, artifact file, input idle
    store.py     local SQLite; holds verdicts and note snapshots, never frames
    evaluate.py  the labelled eval, which refuses to report unquotable numbers
"""

__version__ = "0.1.0"

from .config import Settings, settings
from .providers import Provider, ProviderError, get_provider
from .schemas import Contract, Diff, Event, Grade, LearnerModel, Quiz, Receipt, Verdict

__all__ = [
    "Contract",
    "Diff",
    "Event",
    "Grade",
    "LearnerModel",
    "Provider",
    "ProviderError",
    "Quiz",
    "Receipt",
    "Settings",
    "Verdict",
    "__version__",
    "get_provider",
    "settings",
]
