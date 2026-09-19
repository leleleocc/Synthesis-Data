"""`add`, as the contract describes it."""

import json
import subprocess
from pathlib import Path

import rewardkit as rk
from rewardkit import criterion


@criterion(shared=True)
def add_reports_its_id(workspace: Path) -> float:
    """B04 add appends one entry and prints the id it assigned."""
    workspace = Path(workspace)
    proc = subprocess.run(
        ["python3", "ledger.py", "add", "1.00", "seed"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        return 0.0
    store = workspace / "ledger.json"
    if not store.is_file():
        return 0.0
    try:
        entries = json.loads(store.read_text(encoding="utf-8")).get("entries", [])
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0.0
    if not entries:
        return 0.0
    return 1.0 if str(entries[-1].get("id")) in proc.stdout.split() else 0.0


rk.add_reports_its_id(weight=1.0)
