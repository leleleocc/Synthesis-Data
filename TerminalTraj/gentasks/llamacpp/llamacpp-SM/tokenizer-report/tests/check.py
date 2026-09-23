#!/usr/bin/env python3
"""Verify tokenizer_report.json and summarize_vocab.py against a sealed oracle."""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path


REPORT_KEYS = [
    "architecture",
    "name",
    "gguf_version",
    "n_tensors",
    "tokenizer_model",
    "tokenizer_pre",
    "vocab_size",
    "n_merges",
    "bos_token_id",
    "eos_token_id",
    "n_cases",
    "cases",
    "tokens_payload_bytes",
    "merges_payload_bytes",
]
CASE_KEYS = [
    "index",
    "input_bytes",
    "n_tokens",
    "first_token",
    "last_token",
    "token_sum",
]
SUM_KEYS = ["tokenizer_model", "vocab_size", "n_merges"]


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


def main() -> None:
    hashes = json.loads(Path("/tests/model_hashes.json").read_text(encoding="utf-8"))
    for rel, digest in hashes.items():
        p = Path(rel)
        if not p.is_file():
            fail(f"missing sealed model file {rel}")
        if sha256_file(p) != digest:
            fail(f"sealed file was modified: {rel}")

    report_path = Path("/results/tokenizer_report.json")
    script = Path("/results/summarize_vocab.py")
    if not report_path.is_file():
        fail("missing /results/tokenizer_report.json")
    if not script.is_file():
        fail("missing /results/summarize_vocab.py")
    assert_stdlib_only(script)

    raw = report_path.read_bytes()
    if not raw.endswith(b"\n"):
        fail("tokenizer_report.json must end with a trailing newline")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"tokenizer_report.json is not UTF-8: {exc}")
    try:
        got = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"tokenizer_report.json is not JSON: {exc}")
    expected = json.loads(Path("/tests/expected_tokenizer_report.json").read_text(encoding="utf-8"))
    if not isinstance(got, dict):
        fail("tokenizer_report.json must be an object")
    if list(got.keys()) != REPORT_KEYS:
        fail(f"report keys must be {REPORT_KEYS}, got {list(got.keys())}")

    for key in REPORT_KEYS:
        if key == "cases":
            continue
        if got[key] != expected[key]:
            fail(f"report.{key}: got {got[key]!r} want {expected[key]!r}")

    cases = got["cases"]
    want_cases = expected["cases"]
    if not isinstance(cases, list) or len(cases) != expected["n_cases"]:
        fail(f"cases must be an array of length n_cases={expected['n_cases']}")
    if len(cases) != len(want_cases):
        fail("case count mismatch versus sealed oracle")
    for i, (row, want) in enumerate(zip(cases, want_cases)):
        if not isinstance(row, dict):
            fail(f"cases[{i}] is not an object")
        if list(row.keys()) != CASE_KEYS:
            fail(f"cases[{i}] keys must be {CASE_KEYS}, got {list(row.keys())}")
        if row != want:
            fail(f"cases[{i}] mismatch: got {row} want {want}")
        if row["n_tokens"] == 0 and (row["first_token"] != 0 or row["last_token"] != 0):
            fail(f"empty case {i} must set first_token and last_token to 0")

    proc = subprocess.run(
        ["python3", str(script), "/app/models/ggml-vocab-llama-bpe.gguf"],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        fail(f"summarize_vocab.py exited {proc.returncode}: {(proc.stderr or proc.stdout)[:400]!r}")
    out = proc.stdout.decode("utf-8")
    if not out.endswith("\n") or out.count("\n") != 1:
        fail(f"summarize_vocab.py must print one JSON line with a trailing newline, got {out!r}")
    try:
        summary = json.loads(out)
    except json.JSONDecodeError as exc:
        fail(f"summarize_vocab.py stdout is not JSON: {exc}")
    if not isinstance(summary, dict) or list(summary.keys()) != SUM_KEYS:
        fail(f"summarizer keys must be {SUM_KEYS} in that order, got {list(summary.keys()) if isinstance(summary, dict) else type(summary)}")
    want_sum = json.loads(Path("/tests/expected_summarize.json").read_text(encoding="utf-8"))
    if summary != want_sum:
        fail(f"summarizer values {summary} != {want_sum}")
    if (
        summary["tokenizer_model"] != got["tokenizer_model"]
        or summary["vocab_size"] != got["vocab_size"]
        or summary["n_merges"] != got["n_merges"]
    ):
        fail("summarizer values must match the report")

    print("c6 verifier ok")


if __name__ == "__main__":
    main()
