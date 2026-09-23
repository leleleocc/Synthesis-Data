#!/usr/bin/env python3
"""Verify kv_layout.json and the kv_nbytes probe against a sealed oracle."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


KEYS = [
    "id",
    "n_stream",
    "n_layers",
    "k_ne0",
    "k_ne1",
    "k_ne2",
    "v_present",
    "v_ne0",
    "v_ne1",
    "v_ne2",
    "k_nbytes",
    "v_nbytes",
    "total_nbytes",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def run_probe(binary: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([str(binary), *args], check=False, capture_output=True)


def main() -> None:
    sealed_cases = Path("/tests/kv_cases.json")
    live_cases = Path("/data/kv_cases.json")
    if not live_cases.is_file():
        fail("missing /data/kv_cases.json")
    if sha256_file(live_cases) != sha256_file(sealed_cases):
        fail("/data/kv_cases.json was modified")

    layout_path = Path("/results/kv_layout.json")
    binary = Path("/results/kv_nbytes")
    if not layout_path.is_file():
        fail("missing /results/kv_layout.json")
    if not binary.is_file():
        fail("missing /results/kv_nbytes")
    if not os.access(binary, os.X_OK):
        fail("/results/kv_nbytes is not executable")
    if binary.read_bytes()[:4] != b"\x7fELF":
        fail("/results/kv_nbytes must be a g++-built ELF executable")

    raw = layout_path.read_bytes()
    if not raw.endswith(b"\n"):
        fail("kv_layout.json must end with a trailing newline")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"kv_layout.json is not UTF-8: {exc}")
    try:
        got = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"kv_layout.json is not JSON: {exc}")
    expected = json.loads(Path("/tests/expected_kv_layout.json").read_text(encoding="utf-8"))
    cases = json.loads(sealed_cases.read_text(encoding="utf-8"))
    if not isinstance(got, list) or len(got) != len(cases):
        fail(f"kv_layout.json must be an array of {len(cases)} objects")
    if len(expected) != len(cases):
        fail("sealed expected_kv_layout.json is out of date")

    for i, (row, want, case) in enumerate(zip(got, expected, cases)):
        if not isinstance(row, dict):
            fail(f"layout[{i}] is not an object")
        if list(row.keys()) != KEYS:
            fail(f"layout[{i}] keys must be {KEYS}, got {list(row.keys())}")
        if row["id"] != case["id"]:
            fail(f"layout[{i}].id {row['id']!r} != case id {case['id']!r}")
        for key in KEYS:
            if row[key] != want[key]:
                fail(f"layout[{i}].{key}: got {row[key]!r} want {want[key]!r}")
        if row["total_nbytes"] != row["k_nbytes"] + row["v_nbytes"]:
            fail(f"layout[{i}].total_nbytes is not k_nbytes + v_nbytes")
        if case["is_mla"]:
            if row["v_present"] is not False or row["v_nbytes"] != 0:
                fail(f"MLA case {case['id']} must omit V")
        else:
            if row["v_present"] is not True:
                fail(f"non-MLA case {case['id']} must have v_present true")

    probes = [
        (["f16", "1024", "4096", "1"], "8388608\n", 0),
        (["f32", "512", "256", "8"], "4194304\n", 0),
        (["q8_0", "256", "1024", "1"], "278528\n", 0),
        (["f16", "576", "1024", "1"], "1179648\n", 0),
        (["f16", "1", "1", "1"], "2\n", 0),
        (["f32", "1", "2", "3"], "24\n", 0),
        (["q8_0", "32", "1", "1"], "34\n", 0),
        (["not_a_type", "8", "1", "1"], "", 2),
        (["q8_0", "33", "1", "1"], "", 2),
    ]
    for args, stdout, code in probes:
        proc = run_probe(binary, args)
        if proc.returncode != code:
            fail(
                f"kv_nbytes {' '.join(args)} exited {proc.returncode}, expected {code}; "
                f"stderr={(proc.stderr[:200] if proc.stderr else b'')!r}"
            )
        got_out = proc.stdout.decode("utf-8")
        if got_out != stdout:
            fail(f"kv_nbytes {' '.join(args)} printed {got_out!r}, expected {stdout!r}")

    print("c5 verifier ok")


if __name__ == "__main__":
    main()
