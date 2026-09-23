#!/usr/bin/env python3
"""Verify gguf_dtype_map.py CLI and dtype_table.json against a sealed oracle."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


FTS = [
    "ALL_F32",
    "MOSTLY_F16",
    "MOSTLY_BF16",
    "MOSTLY_Q8_0",
    "MOSTLY_TQ1_0",
    "MOSTLY_TQ2_0",
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


def assert_stdlib_only(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        fail(f"{path} is not valid Python: {exc}")
    forbidden = {
        "torch",
        "numpy",
        "gguf",
        "requests",
        "urllib",
        "http",
        "socket",
        "subprocess",
        "ctypes",
        "importlib",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in forbidden:
                    fail(f"{path} imports forbidden module {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".", 1)[0]
                if root in forbidden:
                    fail(f"{path} imports forbidden module {node.module}")


def run_cli(script: Path, extra: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", str(script), *extra],
        check=False,
        capture_output=True,
    )


def main() -> None:
    sealed = Path("/tests/tensor_names.txt")
    live = Path("/data/tensor_names.txt")
    if not live.is_file():
        fail("missing /data/tensor_names.txt")
    if sha256_file(live) != sha256_file(sealed):
        fail("/data/tensor_names.txt was modified")

    tensors = [ln for ln in sealed.read_text(encoding="utf-8").splitlines() if ln != ""]
    expected = json.loads(Path("/tests/expected_dtype_table.json").read_text(encoding="utf-8"))
    expected_map = {(row["ftype"], row["tensor"]): row["ggml_type"] for row in expected}

    script = Path("/results/gguf_dtype_map.py")
    table_path = Path("/results/dtype_table.json")
    if not script.is_file():
        fail("missing /results/gguf_dtype_map.py")
    if not os.access(script, os.X_OK):
        fail("/results/gguf_dtype_map.py is not executable")
    if not table_path.is_file():
        fail("missing /results/dtype_table.json")

    assert_stdlib_only(script)

    raw = table_path.read_bytes()
    if not raw.endswith(b"\n"):
        fail("dtype_table.json must end with a trailing newline")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"dtype_table.json is not UTF-8: {exc}")
    try:
        table = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"dtype_table.json is not JSON: {exc}")
    if not isinstance(table, list):
        fail("dtype_table.json must be a JSON array")
    want_n = len(FTS) * len(tensors)
    if len(table) != want_n:
        fail(f"dtype_table.json has {len(table)} rows, expected {want_n}")

    idx = 0
    for ftype in FTS:
        for tensor in tensors:
            row = table[idx]
            idx += 1
            if not isinstance(row, dict):
                fail(f"row {idx} is not an object")
            keys = list(row.keys())
            if keys != ["ftype", "tensor", "ggml_type"]:
                fail(f"row {idx} keys must be ftype,tensor,ggml_type in that order, got {keys}")
            if row["ftype"] != ftype or row["tensor"] != tensor:
                fail(f"row {idx} expected ftype={ftype} tensor={tensor}, got {row['ftype']} {row['tensor']}")
            want = expected_map[(ftype, tensor)]
            if row["ggml_type"] != want:
                fail(
                    f"dtype_table mismatch for {ftype}/{tensor}: got {row['ggml_type']!r} want {want!r}"
                )

    for ftype, tensor, want in [
        ("MOSTLY_Q8_0", "token_embd.weight", "Q8_0"),
        ("MOSTLY_TQ1_0", "token_embd.weight", "F16"),
        ("MOSTLY_TQ2_0", "output.weight", "F16"),
        ("MOSTLY_Q8_0", "output.bias", "F32"),
        ("MOSTLY_Q8_0", "blk.0.attn_norm.weight", "F32"),
        ("MOSTLY_Q8_0", "blk.0.ffn_gate_inp.weight", "F32"),
        ("MOSTLY_TQ1_0", "blk.0.attn_q.lora_a", "TQ1_0"),
        ("MOSTLY_Q8_0", "tokenizer.ggml.tokens", "NA"),
        ("MOSTLY_F16", "tokenizer.ggml.merges", "NA"),
        ("ALL_F32", "blk.0.attn_q.weight", "F32"),
        ("MOSTLY_BF16", "blk.0.ffn_down.weight", "BF16"),
    ]:
        proc = run_cli(script, ["--ftype", ftype, "--tensor", tensor])
        if proc.returncode != 0:
            fail(
                f"CLI {ftype}/{tensor} exited {proc.returncode}: {(proc.stderr or proc.stdout)[:400]!r}"
            )
        out = proc.stdout.decode("utf-8")
        if out != want + "\n":
            fail(f"CLI {ftype}/{tensor} printed {out!r}, expected {want + chr(10)!r}")

    bad = run_cli(script, ["--ftype", "NOT_A_REAL_FTYPE", "--tensor", "token_embd.weight"])
    if bad.returncode != 2:
        fail(f"unknown ftype must exit 2, got {bad.returncode}")

    print("c3 verifier ok")


if __name__ == "__main__":
    main()
