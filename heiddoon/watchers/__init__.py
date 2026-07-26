"""The signals. Each one answers a question the others cannot.

    screen    what are you looking at, and does it mean what your contract allows
    camera    are you here, and is there a phone in your hand
    artifact  did the work actually move — the only device-independent signal
    idle      are you at the machine at all (no model call, no cost)
"""

from . import artifact, camera, idle, screen

__all__ = ["artifact", "camera", "idle", "screen"]
