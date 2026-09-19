"""The store, as the contract describes it."""

import json
from pathlib import Path

import rewardkit as rk
from rewardkit import criterion


@criterion(shared=True)
def store_is_created(workspace: Path) -> float:
    """B01 a command that needs the store and finds none writes next_id 1 / entries []."""
    store = Path(workspace) / "ledger.json"
    if not store.is_file():
        return 0.0
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0.0
    return 1.0 if data.get("next_id") == 1 and data.get("entries") == [] else 0.0


rk.store_is_created(weight=1.0)
