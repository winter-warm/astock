"""Small compatibility helpers shared by desktop and worker entry points."""
from __future__ import annotations

import os
import sys


def ensure_standard_streams():
    # A windowed Windows executable has no console. Third-party data providers
    # still use print/tqdm; give them a bounded sink before spawning workers.
    # Application errors continue through our queue and persistent logs.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8", errors="replace"))
