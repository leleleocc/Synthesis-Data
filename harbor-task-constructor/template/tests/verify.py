"""Score only the final, complete raw two-arm Harbor evidence round."""

from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any


PARSER_MODULE_NAME = "sop_parse_scores"
MISSING = object()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as output:
        json.dump(value, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
        temporary = Path(output.name)
    os.replace(temporary, path)


def load_parser(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(PARSER_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load parser module from {path}")
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(PARSER_MODULE_NAME, MISSING)
    try:
        sys.modules[PARSER_MODULE_NAME] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is MISSING:
            sys.modules.pop(PARSER_MODULE_NAME, None)
        else:
            sys.modules[PARSER_MODULE_NAME] = previous


def print_summary(report: dict[str, Any] | None, reward: float, faults: list[str]) -> None:
    if report is None:
        print("target mean unreadable  solver mean unreadable  R unreadable")
        print("valid 0  invalid 0")
    else:
        arms = report.get("arms", {})
        target = arms.get("target", {})
        solver = arms.get("solver", {})
        r_value = report.get("R") if report.get("R") is not None else report.get("R_state", "unreadable")
        print(f"target mean {target.get('mean')}  solver mean {solver.get('mean')}  R {r_value}")
        print(
            f"valid {target.get('valid', 0) + solver.get('valid', 0)}  "
            f"invalid {target.get('invalid', 0) + solver.get('invalid', 0)}"
        )
    print(f"outer reward {reward:.4f}")
    for fault in faults:
        print(f"NO READING: {fault}", file=sys.stderr)


def main() -> int:
    build_root = Path(os.environ.get("SOP_BUILD_ROOT", "/app/build"))
    reward_path = Path(os.environ.get("SOP_REWARD_PATH", "/logs/verifier/reward.json"))
    report_path = Path(os.environ.get("SOP_REPORT_PATH", "/logs/verifier/gap.json"))
    parser_path = Path(os.environ.get("SOP_PARSER_PATH", "/app/method/parse_scores.py"))
    evidence_root = build_root / "evidence"
    final_task = build_root / "task"
    report: dict[str, Any] | None = None
    faults: list[str] = []
    outer_reward = 0.0
    round_dir: Path | None = None

    parser = load_parser(parser_path)
    try:
        round_dir = parser.latest_numbered(evidence_root, "round-")
        report = parser.parse_round(round_dir, final_task=final_task)
        candidate = report.get("reward")
        if not isinstance(candidate, (int, float)) or isinstance(candidate, bool) or not math.isfinite(candidate):
            raise RuntimeError("parser returned a non-numeric reward")
        if not 0.0 <= candidate <= 1.0:
            raise RuntimeError("parser returned an out-of-bounds reward")
        outer_reward = float(candidate)
    except parser.ReadingError as exc:
        faults = [str(exc)]

    if report is None:
        gap: dict[str, Any] = {
            "round": round_dir.name if round_dir is not None else None,
            "parser_report": None,
            "faults": faults,
        }
    else:
        gap = report

    atomic_json(report_path, gap)
    atomic_json(reward_path, {"reward": outer_reward})
    print_summary(report, outer_reward, faults)
    return 0


if __name__ == "__main__":
    sys.exit(main())
