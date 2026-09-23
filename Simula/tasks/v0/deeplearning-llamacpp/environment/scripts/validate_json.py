#!/usr/bin/env python3
"""Small schema checks used by the synthesis task verifiers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def require_keys(obj: dict[str, Any], keys: list[str], label: str) -> None:
    missing = [key for key in keys if key not in obj]
    if missing:
        raise ValueError(f"{label} missing keys: {', '.join(missing)}")


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: validate_json.py PATH KEY [KEY ...]", file=sys.stderr)
        return 2
    obj = require_object(load(sys.argv[1]), sys.argv[1])
    require_keys(obj, sys.argv[2:], sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
