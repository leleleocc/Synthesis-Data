"""`list` and `sum`, as the contract describes them."""

import re
import subprocess
from pathlib import Path

import rewardkit as rk
from rewardkit import criterion

LINE = re.compile(r"^\d+\t\d{4}-\d{2}-\d{2}\t\S+\t-?\d+\.\d{2}$")


def _run(workspace: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", "ledger.py", *argv],
        cwd=Path(workspace),
        capture_output=True,
        text=True,
        timeout=30,
    )


@criterion(shared=True)
def list_renders_a_line(workspace: Path) -> float:
    """B09 every list line is id, date, tag and a two-decimal amount, tab separated."""
    _run(workspace, "add", "1.00", "seed")
    proc = _run(workspace, "list")
    if proc.returncode != 0:
        return 0.0
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return 1.0 if lines and all(LINE.match(ln) for ln in lines) else 0.0


@criterion(shared=True)
def sum_has_two_decimals(workspace: Path) -> float:
    """B13 sum prints the total with exactly two decimal places and nothing else."""
    proc = _run(workspace, "sum")
    if proc.returncode != 0:
        return 0.0
    return 1.0 if re.fullmatch(r"-?\d+\.\d{2}", proc.stdout.strip()) else 0.0


rk.list_renders_a_line(weight=1.0)
rk.sum_has_two_decimals(weight=1.0)
