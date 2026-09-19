"""The task-level status object the host GETs instead of listing runs/.

Overwritten at phase and iteration bounds. lives and sandboxes accumulate
across sandboxes: each write reads the previous file, then adds what this
call bumped. A missing or corrupt file starts both counters at zero. The
two workspace markers are copied as booleans; this module does not interpret
them.
"""

import json
import os
from datetime import datetime, timezone

_MISSING = object()


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            body = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {}
    return body if isinstance(body, dict) else {}


def _count(previous, key):
    try:
        return int(previous.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def write(cfg, phase, iteration=None, bump_sandboxes=False, bump_lives=False,
          verified=_MISSING, create=True):
    if not create and not os.path.exists(cfg.status_path):
        return None
    previous = _load(cfg.status_path)
    lives = _count(previous, "lives")
    sandboxes = _count(previous, "sandboxes")
    if bump_lives:
        lives += 1
    if bump_sandboxes:
        sandboxes += 1
    if iteration is None:
        iteration = previous.get("iteration")
    if verified is _MISSING:
        verified = previous.get("verified")

    body = {
        "task_id": cfg.task_id,
        "phase": phase,
        "iteration": iteration,
        "max_iterations": cfg.max_iterations,
        "lives": lives,
        "sandboxes": sandboxes,
        "done": os.path.exists(cfg.done_marker),
        "verified": verified,
        "markers": {
            "measuring": os.path.exists(cfg.measuring_marker),
            "blocked": os.path.exists(cfg.blocked_marker),
        },
        "run_id": cfg.run_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs(os.path.dirname(cfg.status_path), exist_ok=True)
    temporary = os.path.join(os.path.dirname(cfg.status_path), ".status.json.tmp")
    with open(temporary, "w", encoding="utf-8") as fh:
        json.dump(body, fh, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temporary, cfg.status_path)
    return body
