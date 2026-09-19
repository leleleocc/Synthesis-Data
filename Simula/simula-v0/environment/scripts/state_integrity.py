#!/usr/bin/env python3
"""Create and verify SHA-256 seals for synthesis state JSON handoffs.

Only single-file seals are supported. The input repository tree is not sealed:
final Harbor packages obtain source with git clone at the pinned commit.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_seal(seal: Path, digest: str) -> None:
    seal.parent.mkdir(parents=True, exist_ok=True)
    temporary = seal.with_name(f".{seal.name}.tmp")
    temporary.write_text(digest + "\n", encoding="utf-8")
    temporary.replace(seal)


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in {"seal", "verify"}:
        print(
            "usage: state_integrity.py seal|verify PATH SEAL",
            file=sys.stderr,
        )
        return 2

    state = Path(argv[2])
    seal = Path(argv[3])
    if not state.is_file():
        print(f"state path not found: {state}", file=sys.stderr)
        return 1

    try:
        actual = digest_file(state)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if argv[1] == "seal":
        write_seal(seal, actual)
        return 0

    if not seal.is_file():
        print(f"state seal not found: {seal}", file=sys.stderr)
        return 1
    expected = seal.read_text(encoding="utf-8").splitlines()
    expected_digest = expected[0].strip() if expected else ""
    if expected_digest != actual:
        print(f"state seal mismatch: {state}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
