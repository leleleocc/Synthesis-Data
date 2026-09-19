#!/usr/bin/env python3
"""Independent verifier for the relocatable find_package(Llama) install."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PREFIX = Path("/results/llama-prefix")
PROBE = Path("/results/bin/llama-probe")
PROBE_JSON = Path("/results/probe.json")
GOLDEN = Path("/tests/goldens/probe.json")
CONSUMER = Path("/results/src/probe")
FIND_SRC = Path("/tests/find_llama")

PROBE_KEYS = ["n_backend", "has_cpu", "ggml_type_count", "qk4_0", "qk8_0", "qnt_version"]


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def top_keys(text: str) -> list:
    return list(json.loads(text).keys())


def find_libs(root: Path) -> list[Path]:
    out = []
    for sub in (root / "lib", root / "lib/x86_64-linux-gnu"):
        if not sub.is_dir():
            continue
        for p in sub.iterdir():
            name = p.name
            if name.startswith("libllama") or name.startswith("libggml"):
                out.append(p)
    return out


def check_prefix() -> None:
    if not PREFIX.is_dir():
        fail("missing /results/llama-prefix")
    for hdr in ("include/llama.h", "include/ggml.h", "include/gguf.h"):
        p = PREFIX / hdr
        if not p.is_file():
            fail(f"missing {p}")
        if p.stat().st_size < 64:
            fail(f"{p} is too small to be a real header")
        text = p.read_text(encoding="utf-8", errors="replace")
        if hdr.endswith("llama.h") and "llama_" not in text:
            fail("include/llama.h does not look like llama.h")
        if hdr.endswith("ggml.h") and "ggml_" not in text:
            fail("include/ggml.h does not look like ggml.h")
        if hdr.endswith("gguf.h") and "gguf_" not in text:
            fail("include/gguf.h does not look like gguf.h")
    libs = find_libs(PREFIX)
    llama_so = [p for p in libs if p.name.startswith("libllama")]
    ggml_so = [p for p in libs if p.name.startswith("libggml")]
    if not llama_so:
        fail("missing llama shared library under lib or lib/x86_64-linux-gnu")
    if not ggml_so:
        fail("missing ggml shared library under lib or lib/x86_64-linux-gnu")
    cmake_dir = PREFIX / "lib/cmake/llama"
    alt_cmake = PREFIX / "lib/x86_64-linux-gnu/cmake/llama"
    found_cfg = False
    for d in (cmake_dir, alt_cmake):
        if not d.is_dir():
            continue
        for name in ("LlamaConfig.cmake", "llama-config.cmake", "LlamaConfig-version.cmake"):
            if (d / name).is_file() or list(d.glob("*.cmake")):
                found_cfg = True
    if not found_cfg:
        fail("missing CMake package files under lib/cmake/llama (or lib/x86_64-linux-gnu/cmake/llama)")


def check_consumer() -> None:
    if not CONSUMER.is_dir():
        fail("missing consumer /results/src/probe")
    cmakes = list(CONSUMER.rglob("CMakeLists.txt"))
    if not cmakes:
        fail("/results/src/probe has no CMakeLists.txt")
    joined = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in cmakes)
    if "find_package" not in joined or "Llama" not in joined:
        fail("consumer CMakeLists.txt must call find_package(Llama)")


def run_find_package() -> None:
    with tempfile.TemporaryDirectory(prefix="find-llama-") as td:
        build = Path(td) / "b"
        proc = subprocess.run(
            [
                "cmake",
                "-S", str(FIND_SRC),
                "-B", str(build),
                f"-DCMAKE_PREFIX_PATH={PREFIX}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            fail(
                "find_package(Llama) failed with CMAKE_PREFIX_PATH=/results/llama-prefix\n"
                f"stdout: {proc.stdout[-1500:]!r}\nstderr: {proc.stderr[-2000:]!r}"
            )


def check_probe_json(text: str) -> dict:
    if not text.endswith("\n"):
        fail("probe.json must end with a newline")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        fail(f"probe.json is not valid JSON: {e}")
    if not isinstance(obj, dict):
        fail("probe.json must be a JSON object")
    if top_keys(text) != PROBE_KEYS:
        fail(f"probe.json keys must be {PROBE_KEYS} in that order, got {top_keys(text)}")
    for k in ("n_backend", "ggml_type_count", "qk4_0", "qk8_0", "qnt_version"):
        if not isinstance(obj[k], int) or isinstance(obj[k], bool):
            fail(f"probe.json {k} must be an integer")
    if obj["has_cpu"] is not True:
        fail("has_cpu must be JSON true")
    # JSON true/false, not 1/0
    if '"has_cpu"' in text:
        if ": true" not in text.replace(":true", ": true") and ":true" not in text.replace(" ", ""):
            fail("has_cpu must be JSON true/false")
        compact = text.replace(" ", "").replace("\n", "")
        if "has_cpu\":true" not in compact:
            fail("has_cpu must be JSON true (not 1)")
    gold = json.loads(GOLDEN.read_text(encoding="utf-8"))
    if obj != gold:
        fail(f"probe.json {obj} != golden {gold}")
    return obj


def run_probe() -> None:
    if not PROBE.is_file() or not os.access(PROBE, os.X_OK):
        fail("/results/bin/llama-probe must be an executable file")
    env = os.environ.copy()
    lib_dirs = []
    for sub in (PREFIX / "lib", PREFIX / "lib/x86_64-linux-gnu"):
        if sub.is_dir():
            lib_dirs.append(str(sub))
    if lib_dirs:
        env["LD_LIBRARY_PATH"] = ":".join(lib_dirs + [env.get("LD_LIBRARY_PATH", "")]).rstrip(":")
    proc = subprocess.run(
        [str(PROBE)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
        env=env,
        cwd="/results",
    )
    if proc.returncode != 0:
        fail(
            f"llama-probe exited {proc.returncode}\n"
            f"stdout: {proc.stdout[:500]!r}\nstderr: {proc.stderr[:800]!r}"
        )


def main() -> None:
    check_prefix()
    check_consumer()
    run_find_package()
    if not PROBE_JSON.is_file():
        fail("missing /results/probe.json")
    original = PROBE_JSON.read_text(encoding="utf-8")
    check_probe_json(original)
    run_probe()
    again = PROBE_JSON.read_text(encoding="utf-8")
    check_probe_json(again)
    print("c3 checks passed", file=sys.stderr)


if __name__ == "__main__":
    main()
