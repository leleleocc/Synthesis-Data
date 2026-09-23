#!/usr/bin/env python3
"""Verify the CPU-only Ninja configure tree at /app/build."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_cache(path: Path) -> dict[str, str]:
    cache: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if ":" not in line or "=" not in line:
            continue
        key_type, _, value = line.partition("=")
        key = key_type.split(":", 1)[0].strip()
        if key:
            cache[key] = value
    return cache


def as_bool(value: str) -> bool | None:
    v = value.strip().upper()
    if v in {"ON", "TRUE", "YES", "1"}:
        return True
    if v in {"OFF", "FALSE", "NO", "0"}:
        return False
    return None


def require_on(cache: dict[str, str], key: str) -> None:
    if key not in cache:
        fail(f"CMake cache missing {key}")
    flag = as_bool(cache[key])
    if flag is not True:
        fail(f"{key} must be ON, got {cache[key]!r}")


def require_off(cache: dict[str, str], key: str) -> None:
    if key not in cache:
        fail(f"CMake cache missing {key}")
    flag = as_bool(cache[key])
    if flag is not False:
        fail(f"{key} must be OFF, got {cache[key]!r}")


def compiler_is_gnu_14(path: str, kind: str) -> None:
    if not path or "nvcc" in path.lower() or "cuda" in path.lower():
        fail(f"{kind} compiler must not be a CUDA/nvcc path: {path!r}")
    resolved = path
    if not os.path.isfile(resolved):
        found = shutil.which(path)
        if found:
            resolved = found
    if not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
        fail(f"{kind} compiler is not an executable file: {path!r}")
    path = resolved
    try:
        ver = subprocess.run(
            [path, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        fail(f"could not execute {kind} compiler {path!r}: {exc}")
    blob = (ver.stdout or "") + (ver.stderr or "")
    low = blob.lower()
    if "nvcc" in low or "cuda compilation" in low:
        fail(f"{kind} compiler looks like nvcc: {path!r}")
    if kind == "C" and "gcc" not in low:
        fail(f"CMAKE_C_COMPILER is not gcc: {path!r} version={blob!r}")
    if kind == "CXX" and "g++" not in low and "gcc" not in low:
        fail(f"CMAKE_CXX_COMPILER is not g++: {path!r} version={blob!r}")
    dump = subprocess.run(
        [path, "-dumpversion"],
        check=False,
        capture_output=True,
        text=True,
    )
    dump_txt = (dump.stdout or "").strip()
    if not dump_txt.startswith("14"):
        fail(f"{kind} compiler is not gcc/g++ 14 (dumpversion={dump_txt!r}, path={path!r})")


def ninja_targets(build: str) -> set[str]:
    proc = subprocess.run(
        ["ninja", "-C", build, "-t", "targets"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        fail(f"ninja -t targets failed: {(proc.stderr or proc.stdout)[:800]}")
    names: set[str] = set()
    for line in (proc.stdout or "").splitlines():
        name = line.split(":", 1)[0].strip()
        if name:
            names.add(name)
    return names


def main() -> None:
    expected_hashes = json.loads(Path("/tests/data_hashes.json").read_text(encoding="utf-8"))
    for rel, digest in expected_hashes.items():
        p = Path(rel)
        if not p.is_file():
            fail(f"missing sealed /data file {rel}")
        got = sha256_file(p)
        if got != digest:
            fail(f"/data was modified: {rel}")

    build = Path("/app/build")
    ninja_file = build / "build.ninja"
    cache_file = build / "CMakeCache.txt"
    if not ninja_file.is_file() or ninja_file.stat().st_size == 0:
        fail("missing or empty /app/build/build.ninja")
    if not cache_file.is_file():
        fail("missing /app/build/CMakeCache.txt")

    cache = parse_cache(cache_file)
    if "CMAKE_CACHEFILE_DIR" not in cache or not cache["CMAKE_CACHEFILE_DIR"].strip():
        fail("CMake cache is missing CMAKE_CACHEFILE_DIR (not cmake-written)")
    cache_dir = Path(cache["CMAKE_CACHEFILE_DIR"]).resolve()
    if cache_dir != build.resolve():
        fail(f"CMAKE_CACHEFILE_DIR is {cache_dir}, expected {build.resolve()}")
    home = cache.get("CMAKE_HOME_DIRECTORY", "").strip()
    if not home or Path(home).resolve() != Path("/app").resolve():
        fail(f"CMAKE_HOME_DIRECTORY must be /app, got {home!r}")
    gen = cache.get("CMAKE_GENERATOR", "")
    if gen != "Ninja":
        fail(f"CMAKE_GENERATOR must be Ninja, got {gen!r}")

    require_on(cache, "GGML_CPU")
    for key in (
        "GGML_CUDA",
        "GGML_HIP",
        "GGML_METAL",
        "GGML_VULKAN",
        "GGML_SYCL",
        "GGML_BLAS",
        "GGML_BACKEND_DL",
        "GGML_CPU_ALL_VARIANTS",
    ):
        require_off(cache, key)
    require_on(cache, "GGML_NATIVE")
    require_on(cache, "GGML_CPU_REPACK")

    if cache.get("CMAKE_BUILD_TYPE", "") != "Release":
        fail(f"CMAKE_BUILD_TYPE must be Release, got {cache.get('CMAKE_BUILD_TYPE')!r}")

    compiler_is_gnu_14(cache.get("CMAKE_C_COMPILER", ""), "C")
    compiler_is_gnu_14(cache.get("CMAKE_CXX_COMPILER", ""), "CXX")

    targets = ninja_targets("/app/build")
    if "ggml-cpu" not in targets:
        fail("ninja -t targets does not list ggml-cpu")

    cmds = subprocess.run(
        ["ninja", "-C", "/app/build", "-t", "commands", "ggml-cpu"],
        check=False,
        capture_output=True,
        text=True,
    )
    if cmds.returncode != 0:
        fail(f"ninja -t commands ggml-cpu failed: {(cmds.stderr or cmds.stdout)[:800]}")
    lines = [ln for ln in (cmds.stdout or "").splitlines() if ln.strip()]
    compile_re = re.compile(
        r"(^|\s)(gcc|g\+\+|cc|c\+\+|clang|clang\+\+|ld|c\d+|c\+\+d)(\s|$)|-c\s| -o ",
        re.I,
    )
    if not any(compile_re.search(ln) for ln in lines):
        fail("ninja -t commands ggml-cpu printed no compile or link command")

    print("c1 verifier ok")


if __name__ == "__main__":
    main()
