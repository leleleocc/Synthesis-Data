#!/usr/bin/env python3
"""Pytest discriminator for the Hopper / FP8 cmake build matrix."""

from __future__ import annotations

import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent / "helpers"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from matrix_checks import check_matrix  # noqa: E402


def test_cmake_build_matrix() -> None:
    failures = []
    for name, ok, reason in check_matrix():
        status = "pass" if ok else "fail"
        line = f"{name}: {status}"
        if not ok:
            line += f" reason: {reason}"
            failures.append(line)
        print(line)
    assert not failures, "; ".join(failures)


if __name__ == "__main__":
    try:
        test_cmake_build_matrix()
    except AssertionError as exc:
        print(f"error handling: fail reason: {exc}")
        raise SystemExit(1)
    print("error handling: pass")
    raise SystemExit(0)
