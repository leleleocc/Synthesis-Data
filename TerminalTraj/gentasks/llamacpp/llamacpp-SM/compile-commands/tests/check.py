#!/usr/bin/env python3
"""Verify the x64-linux-gcc-release preset tree and compile_commands.json."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


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
    if as_bool(cache[key]) is not True:
        fail(f"{key} must be ON, got {cache[key]!r}")


def require_not_on(cache: dict[str, str], key: str) -> None:
    if key not in cache:
        return
    if as_bool(cache[key]) is True:
        fail(f"{key} must not be ON")


def compiler_is_gnu_14(path: str, kind: str) -> None:
    if not path or "nvcc" in path.lower() or "cuda" in path.lower():
        fail(f"{kind} compiler must resolve to gcc/g++, got {path!r}")
    resolved = path
    if not os.path.isfile(resolved):
        found = shutil.which(path)
        if found:
            resolved = found
    if not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
        fail(f"{kind} compiler is not an executable file: {path!r}")
    path = resolved
    ver = subprocess.run([path, "--version"], check=False, capture_output=True, text=True)
    blob = ((ver.stdout or "") + (ver.stderr or "")).lower()
    if kind == "C" and "gcc" not in blob:
        fail(f"CMAKE_C_COMPILER is not gcc: {path!r}")
    if kind == "CXX" and "g++" not in blob and "gcc" not in blob:
        fail(f"CMAKE_CXX_COMPILER is not g++: {path!r}")
    dump = subprocess.run([path, "-dumpversion"], check=False, capture_output=True, text=True)
    dump_txt = (dump.stdout or "").strip()
    if not dump_txt.startswith("14"):
        fail(f"{kind} compiler is not gcc/g++ 14 (dumpversion={dump_txt!r})")


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


def load_compile_commands(path: Path) -> list[dict]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{path} is not UTF-8: {exc}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"{path} is not JSON: {exc}")
    if not isinstance(data, list) or not data:
        fail(f"{path} must be a non-empty JSON array")
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            fail(f"{path}[{i}] is not an object")
        if not isinstance(item.get("directory"), str) or not item["directory"]:
            fail(f"{path}[{i}] missing string directory")
        if not isinstance(item.get("file"), str) or not item["file"]:
            fail(f"{path}[{i}] missing string file")
        has_cmd = isinstance(item.get("command"), str) and bool(item.get("command"))
        args = item.get("arguments")
        has_args = isinstance(args, list) and all(isinstance(a, str) for a in args) and bool(args)
        if not has_cmd and not has_args:
            fail(f"{path}[{i}] needs command (string) or arguments (array of strings)")
    return data


def main() -> None:
    build = Path("/app/build-x64-linux-gcc-release")
    ninja_file = build / "build.ninja"
    cache_file = build / "CMakeCache.txt"
    cc_build = build / "compile_commands.json"
    cc_app = Path("/app/compile_commands.json")

    if not ninja_file.is_file() or ninja_file.stat().st_size == 0:
        fail("missing or empty /app/build-x64-linux-gcc-release/build.ninja")
    if not cache_file.is_file():
        fail("missing CMakeCache.txt in the preset binaryDir")
    if not cc_build.is_file():
        fail("missing /app/build-x64-linux-gcc-release/compile_commands.json")
    if not cc_app.is_file():
        fail("missing /app/compile_commands.json")

    bytes_build = cc_build.read_bytes()
    bytes_app = cc_app.read_bytes()
    if bytes_build != bytes_app:
        fail("/app/compile_commands.json is not byte-identical to the preset binaryDir copy")

    cache = parse_cache(cache_file)
    if "CMAKE_CACHEFILE_DIR" not in cache or not cache["CMAKE_CACHEFILE_DIR"].strip():
        fail("CMake cache is missing CMAKE_CACHEFILE_DIR (not cmake-written)")
    cache_dir = Path(cache["CMAKE_CACHEFILE_DIR"]).resolve()
    if cache_dir != build.resolve():
        fail(f"CMAKE_CACHEFILE_DIR is {cache_dir}, expected {build.resolve()}")
    home = cache.get("CMAKE_HOME_DIRECTORY", "").strip()
    if not home or Path(home).resolve() != Path("/app").resolve():
        fail(f"CMAKE_HOME_DIRECTORY must be /app, got {home!r}")
    if cache.get("CMAKE_GENERATOR") != "Ninja":
        fail(f"CMAKE_GENERATOR must be Ninja, got {cache.get('CMAKE_GENERATOR')!r}")
    if cache.get("CMAKE_BUILD_TYPE") != "Release":
        fail(f"CMAKE_BUILD_TYPE must be Release, got {cache.get('CMAKE_BUILD_TYPE')!r}")
    require_on(cache, "CMAKE_EXPORT_COMPILE_COMMANDS")
    require_on(cache, "GGML_CPU")
    for key in ("GGML_CUDA", "GGML_VULKAN", "GGML_SYCL"):
        require_not_on(cache, key)
    compiler_is_gnu_14(cache.get("CMAKE_C_COMPILER", ""), "C")
    compiler_is_gnu_14(cache.get("CMAKE_CXX_COMPILER", ""), "CXX")

    targets = ninja_targets(str(build))
    for name in ("ggml-cpu", "llama"):
        if name not in targets:
            fail(f"ninja -t targets does not list {name}")

    entries = load_compile_commands(cc_build)

    def resolve_entry_file(item: dict) -> Path:
        p = Path(str(item["file"]))
        if not p.is_absolute():
            p = Path(str(item["directory"])) / p
        return p

    def has_existing(suffixes: tuple[str, ...]) -> bool:
        for item in entries:
            f = str(item["file"]).replace("\\", "/")
            if any(f.endswith(s) for s in suffixes):
                if resolve_entry_file(item).is_file():
                    return True
        return False

    if not has_existing(("ggml-cpu.c", "ggml-cpu.cpp")):
        fail("compile_commands.json has no existing file ending in ggml-cpu.c or ggml-cpu.cpp")
    if not has_existing(("/src/llama.cpp", "src/llama.cpp")):
        fail("compile_commands.json has no existing file ending in src/llama.cpp")

    print("c2 verifier ok")


if __name__ == "__main__":
    main()
