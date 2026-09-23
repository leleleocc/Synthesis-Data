#!/usr/bin/env python3
"""Discriminate Hopper sm90 gencode vs FP8 scaled-mm ABI matrix."""

from __future__ import annotations

import json
from pathlib import Path

MATRIX = Path("/workspace/cmake_build_matrix.json")
ENTRY = Path("/usr/local/bin/vllm-nonroot-entrypoint.sh")
FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "required_cells.json"

REQUIRED_TOP = ("entrypoint", "sm90_ok", "fp8_abi_ok", "cells")
REQUIRED_CELL = ("arch", "kernel_abi", "built", "artifact_path")


def _load(path: Path) -> tuple[object | None, str]:
    if not path.is_file():
        return None, f"missing {path}"
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return None, f"empty {path}"
    try:
        return json.loads(raw), ""
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON in {path}: {exc}"


def check_matrix() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    def rec(name: str, ok: bool, reason: str = "") -> None:
        results.append((name, ok, reason))

    expected, err = _load(FIXTURE)
    if not isinstance(expected, dict):
        rec("fixture", False, err or "required_cells.json is not an object")
        return results

    matrix, err = _load(MATRIX)
    if not isinstance(matrix, dict):
        rec("normal case", False, err or "cmake_build_matrix.json is not an object")
        return results

    missing = [key for key in REQUIRED_TOP if key not in matrix]
    rec("schema required", not missing, f"missing {missing}")

    rec(
        "entrypoint",
        matrix.get("entrypoint") == expected["entrypoint"],
        f"entrypoint must be {expected['entrypoint']!r}",
    )
    rec("sm90_ok", matrix.get("sm90_ok") is True, "sm90_ok must be true")
    rec("fp8_abi_ok", matrix.get("fp8_abi_ok") is True, "fp8_abi_ok must be true")
    rec(
        "coupled flags",
        matrix.get("sm90_ok") is True and matrix.get("fp8_abi_ok") is True,
        "Hopper 9.0 gencode and FP8 ABI must both be true",
    )

    cells = matrix.get("cells")
    rec("cells", isinstance(cells, list) and len(cells) >= 2, "cells must contain at least two entries")
    if not isinstance(cells, list):
        return results

    found: dict[tuple[str, str], dict] = {}
    required_keys = {(cell["arch"], cell["kernel_abi"]) for cell in expected["cells"]}
    for index, cell in enumerate(cells):
        label = f"cell[{index}]"
        if not isinstance(cell, dict):
            rec(label, False, "cell must be an object")
            continue
        c_missing = [key for key in REQUIRED_CELL if key not in cell]
        rec(f"{label} schema", not c_missing, f"missing {c_missing}")
        arch = cell.get("arch")
        abi = cell.get("kernel_abi")
        built = cell.get("built")
        artifact = cell.get("artifact_path")
        rec(f"{label} arch", isinstance(arch, str) and bool(arch), "arch must be a non-empty string")
        rec(f"{label} kernel_abi", isinstance(abi, str) and bool(abi), "kernel_abi must be a non-empty string")
        is_required = (arch, abi) in required_keys
        if is_required:
            rec(f"{label} built", built is True, "required cell built must be true")
            rec(
                f"{label} artifact_path",
                isinstance(artifact, str) and artifact.startswith("/") and Path(artifact).is_file() and Path(artifact).stat().st_size > 0,
                f"artifact_path {artifact!r} is missing, empty, or not an existing file",
            )
            rec(
                f"{label} not copied input",
                artifact not in {"/workspace/cuda_arch_pins.cmake", "/workspace/repo/cmake/cuda_arch_pins.cmake"},
                "artifact_path is a copy of the Ampere pin file, not a built cell",
            )
        if isinstance(arch, str) and isinstance(abi, str):
            found[(arch, abi)] = cell

    for want in expected["cells"]:
        key = (want["arch"], want["kernel_abi"])
        rec(
            f"required {want['arch']}/{want['kernel_abi']}",
            key in found and found[key].get("built") is True,
            f"missing built cell arch={want['arch']} kernel_abi={want['kernel_abi']}",
        )

    rec(
        "sm90 cell exists",
        any(arch == "9.0" and abi == "sm90" for arch, abi in found),
        "no Hopper 9.0 / sm90 cell",
    )
    rec(
        "fp8 cell exists",
        any(arch == "9.0a" and abi == "fp8_scaled_mm" for arch, abi in found),
        "no sm90a / fp8_scaled_mm cell",
    )

    sm90_cell = found.get(("9.0", "sm90"))
    fp8_cell = found.get(("9.0a", "fp8_scaled_mm"))
    if isinstance(sm90_cell, dict) and isinstance(fp8_cell, dict):
        left = sm90_cell.get("artifact_path")
        right = fp8_cell.get("artifact_path")
        rec(
            "distinct cell artifacts",
            isinstance(left, str) and isinstance(right, str) and left != right,
            "both cells point at the same artifact_path",
        )
        if isinstance(left, str) and isinstance(right, str) and Path(left).is_file() and Path(right).is_file():
            rec(
                "artifacts not identical stubs",
                Path(left).read_bytes() != Path(right).read_bytes(),
                "sm90 and fp8 artifacts are identical hardcoded stubs",
            )

    rec(
        "entrypoint binary present",
        ENTRY.is_file(),
        f"missing {ENTRY}",
    )

    return results


def main() -> int:
    failures = []
    for name, ok, reason in check_matrix():
        status = "pass" if ok else "fail"
        line = f"{name}: {status}"
        if not ok:
            line += f" reason: {reason}"
            failures.append(line)
        print(line)
    if failures:
        print("error handling: fail reason: " + "; ".join(failures))
        return 1
    print("error handling: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
