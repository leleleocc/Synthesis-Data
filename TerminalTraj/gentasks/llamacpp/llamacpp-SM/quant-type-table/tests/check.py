#!/usr/bin/env python3
"""Verify quant_types.csv and the ftype_default probe against a sealed oracle."""
from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path


HEADER = "ftype_enum,ftype_value,cli_name,default_ggml_type,default_ggml_type_id,imatrix_required"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def run_probe(binary: Path, payload: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(binary)],
        input=payload,
        check=False,
        capture_output=True,
    )


def main() -> None:
    csv_path = Path("/results/quant_types.csv")
    binary = Path("/results/ftype_default")
    expected_path = Path("/tests/expected_quant_types.csv")

    if not csv_path.is_file():
        fail("missing /results/quant_types.csv")
    if not binary.is_file():
        fail("missing /results/ftype_default")
    if not os.access(binary, os.X_OK):
        fail("/results/ftype_default is not executable")
    if binary.read_bytes()[:4] != b"\x7fELF":
        fail("/results/ftype_default must be a g++-built ELF executable")

    raw = csv_path.read_bytes()
    if b"\r" in raw:
        fail("quant_types.csv must use LF line endings")
    if not raw.endswith(b"\n"):
        fail("quant_types.csv must end with a trailing newline")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"quant_types.csv is not UTF-8: {exc}")

    lines = text.splitlines()
    if not lines or lines[0] != HEADER:
        fail(f"CSV header must be exactly {HEADER!r}")

    expected_text = expected_path.read_text(encoding="utf-8")
    expected_rows = list(csv.DictReader(expected_text.splitlines()))
    got_rows = list(csv.DictReader(lines))
    if len(got_rows) != len(expected_rows):
        fail(f"CSV has {len(got_rows)} data rows, expected {len(expected_rows)}")

    for i, (got, want) in enumerate(zip(got_rows, expected_rows), start=1):
        if list(got.keys()) != HEADER.split(","):
            fail(f"row {i} has unexpected columns {list(got.keys())}")
        for key in HEADER.split(","):
            if got[key] != want[key]:
                fail(f"CSV row {i} field {key}: got {got[key]!r} want {want[key]!r}")
        if got["ftype_enum"] == "LLAMA_FTYPE_GUESSED":
            fail("CSV must not include LLAMA_FTYPE_GUESSED")
        if got["cli_name"] == "COPY" or got["ftype_enum"] == "COPY":
            fail("CSV must not emit a COPY row")

    samples = [(row["ftype_value"], row["default_ggml_type"] + "\n", 0) for row in expected_rows]
    samples.extend(
        [
            ("1024", "", 2),
            ("4", "", 2),
            ("39", "", 2),
        ]
    )
    for payload, stdout, code in samples:
        proc = run_probe(binary, payload.encode("ascii") + b"\n")
        if proc.returncode != code:
            fail(
                f"ftype_default({payload}) exited {proc.returncode}, expected {code}; "
                f"stderr={(proc.stderr[:200] if proc.stderr else b'')!r}"
            )
        got_out = proc.stdout.decode("utf-8")
        if got_out != stdout:
            fail(f"ftype_default({payload}) printed {got_out!r}, expected {stdout!r}")

    print("c4 verifier ok")


if __name__ == "__main__":
    main()
