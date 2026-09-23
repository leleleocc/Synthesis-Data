#!/usr/bin/env python3
"""Check /results/probe.json against ggml compile-time constants."""
from __future__ import annotations

import json
import re
import sys
from collections import OrderedDict
from pathlib import Path


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def macro_int(header: Path, name: str) -> int:
    text = header.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"#define\s+" + re.escape(name) + r"\s+(\d+)", text)
    if not m:
        fail(f"{name} not found in {header}")
    return int(m.group(1))


def ggml_blck_size_from_header() -> tuple[int, int]:
    """QK4_0 and QK8_0 from ggml-common.h (ggml_blck_size(Q4_0/Q8_0))."""
    common = Path("/app/ggml/src/ggml-common.h")
    if not common.is_file():
        # Prefix install may not ship ggml-common.h; fall back to known constants.
        return 32, 32
    text = common.read_text(encoding="utf-8", errors="replace")
    def grab(name: str, default: int) -> int:
        m = re.search(r"#define\s+" + re.escape(name) + r"\s+(\d+)", text)
        return int(m.group(1)) if m else default
    return grab("QK4_0", 32), grab("QK8_0", 32)


def main() -> None:
    path = Path("/results/probe.json")
    if not path.is_file():
        fail("missing /results/probe.json")
    raw_b = path.read_bytes()
    if not raw_b.endswith(b"\n"):
        fail("probe.json must end with a newline")
    raw = raw_b.decode("utf-8")
    decoder = json.JSONDecoder(object_pairs_hook=OrderedDict)
    obj, idx = decoder.raw_decode(raw)
    if raw[idx:].strip() != "":
        fail("probe.json has trailing junk")
    keys = list(obj.keys())
    expected = ["n_backend", "has_cpu", "ggml_type_count", "qk4_0", "qk8_0", "qnt_version"]
    if keys != expected:
        fail(f"probe.json keys {keys} != {expected}")

    ggml_h = Path("/app/ggml/include/ggml.h")
    if not ggml_h.is_file():
        ggml_h = Path("/results/llama-prefix/include/ggml.h")
    type_count = None
    qnt_version = None
    if ggml_h.is_file():
        text = ggml_h.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"GGML_TYPE_COUNT\s*=\s*(\d+)", text)
        if m:
            type_count = int(m.group(1))
        m = re.search(r"#define\s+GGML_QNT_VERSION\s+(\d+)", text)
        if m:
            qnt_version = int(m.group(1))
    if type_count is None:
        type_count = 43
    if qnt_version is None:
        qnt_version = 2
    qk4_0, qk8_0 = ggml_blck_size_from_header()

    for k in ("n_backend", "ggml_type_count", "qk4_0", "qk8_0", "qnt_version"):
        if not isinstance(obj[k], int) or isinstance(obj[k], bool):
            fail(f"{k} must be a JSON integer")
    if obj["has_cpu"] is not True:
        fail("has_cpu must be JSON true")
    # Confirm JSON encoding uses true/false, not 1/0.
    if not re.search(r'"has_cpu"\s*:\s*true', raw):
        fail("has_cpu must be encoded as JSON true/false")
    if obj["ggml_type_count"] != type_count:
        fail(f"ggml_type_count {obj['ggml_type_count']} != GGML_TYPE_COUNT {type_count}")
    if obj["qk4_0"] != qk4_0:
        fail(f"qk4_0 {obj['qk4_0']} != ggml_blck_size(Q4_0) {qk4_0}")
    if obj["qk8_0"] != qk8_0:
        fail(f"qk8_0 {obj['qk8_0']} != ggml_blck_size(Q8_0) {qk8_0}")
    if obj["qnt_version"] != qnt_version:
        fail(f"qnt_version {obj['qnt_version']} != GGML_QNT_VERSION {qnt_version}")
    if obj["n_backend"] < 1:
        fail("n_backend must be >= 1 after CPU backend registration")
    print("oracle: probe.json matches ggml constants")


if __name__ == "__main__":
    main()
