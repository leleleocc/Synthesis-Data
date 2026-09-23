#!/usr/bin/env python3
"""Discriminate flash-attn block-size vs KV-cache stride parity."""

from __future__ import annotations

import json
from pathlib import Path

TABLE = Path("/workspace/kernel_parity_table.json")
LAYOUT = Path("/workspace/repo/vllm/v1/kv_cache_layout.py")
FLASH = Path("/workspace/repo/vllm/v1/attention/backends/flash_attn.py")
FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "stride_orders.json"

REQUIRED_TOP = ("block_size_ok", "stride_ok", "kv_cache_shape", "rows")
REQUIRED_ROW = ("block_size", "layout_name", "stride_order", "parity_ok")


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


def check_parity() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    def rec(name: str, ok: bool, reason: str = "") -> None:
        results.append((name, ok, reason))

    expected, err = _load(FIXTURE)
    if not isinstance(expected, dict):
        rec("fixture", False, err or "stride_orders.json is not an object")
        return results
    layouts = expected["layouts"]
    required_blocks = [int(x) for x in expected["required_block_sizes"]]
    multiple = int(expected["block_multiple"])

    table, err = _load(TABLE)
    if not isinstance(table, dict):
        rec("normal case", False, err or "parity table is not an object")
        return results

    missing = [key for key in REQUIRED_TOP if key not in table]
    rec("schema required", not missing, f"missing {missing}")

    rec("block_size_ok", table.get("block_size_ok") is True, "block_size_ok must be true")
    rec("stride_ok", table.get("stride_ok") is True, "stride_ok must be true")
    rec(
        "coupled flags",
        table.get("block_size_ok") is True and table.get("stride_ok") is True,
        "both complexity_delta flags must be true together",
    )

    shape = table.get("kv_cache_shape")
    rec(
        "kv_cache_shape",
        isinstance(shape, list) and len(shape) == 4,
        "kv_cache_shape must be a 4-element array",
    )
    if isinstance(shape, list) and len(shape) == 4:
        rec(
            "kv_cache_shape types",
            all(item is None or (isinstance(item, int) and not isinstance(item, bool) and item > 0) for item in shape),
            "kv_cache_shape entries must be null or positive integers",
        )
        page_extent = shape[2]
        rec(
            "page axis block_size",
            page_extent is None or (isinstance(page_extent, int) and page_extent % multiple == 0),
            "packed cache page axis must carry a MultipleOf(16) block_size",
        )

    rows = table.get("rows")
    rec("rows", isinstance(rows, list) and rows, "rows must be a non-empty array")
    if not isinstance(rows, list) or not rows:
        return results

    seen: set[tuple[int, str]] = set()
    for index, row in enumerate(rows):
        label = f"row[{index}]"
        if not isinstance(row, dict):
            rec(label, False, "row must be an object")
            continue
        r_missing = [key for key in REQUIRED_ROW if key not in row]
        rec(f"{label} schema", not r_missing, f"missing {r_missing}")
        block_size = row.get("block_size")
        layout_name = row.get("layout_name")
        stride_order = row.get("stride_order")
        rec(
            f"{label} block_size",
            isinstance(block_size, int)
            and not isinstance(block_size, bool)
            and (block_size % multiple == 0 or block_size == 128),
            f"block_size={block_size} is not MultipleOf({multiple}) or 128",
        )
        rec(
            f"{label} layout_name",
            layout_name in layouts,
            f"unknown layout_name {layout_name!r}",
        )
        rec(
            f"{label} stride_order",
            isinstance(stride_order, list)
            and stride_order == layouts.get(layout_name),
            f"{layout_name} stride_order must be {layouts.get(layout_name)}, got {stride_order}",
        )
        rec(f"{label} parity_ok", row.get("parity_ok") is True, "parity_ok must be true")
        if isinstance(block_size, int) and isinstance(layout_name, str):
            seen.add((block_size, layout_name))

    rec(
        "required matrix",
        all((block, name) in seen for block in required_blocks for name in layouts),
        "rows must include block sizes 16 and 128 against each of the six layouts",
    )
    rec(
        "no illegal page size",
        all(block % multiple == 0 or block == 128 for block, _name in seen),
        "advertised kernel block sizes include an illegal page size",
    )

    if not FLASH.is_file():
        rec("flash source", False, f"missing {FLASH}")
    else:
        flash_text = FLASH.read_text(encoding="utf-8")
        rec(
            "flash MultipleOf(16) or 128-page",
            "MultipleOf(16)" in flash_text or "FA4_HD256_PAGE_SIZE" in flash_text,
            "flash-attn does not advertise MultipleOf(16) or the 128-token flash page size",
        )
        rec(
            "negative space MultipleOf(8)",
            "return [MultipleOf(8)]" not in flash_text,
            "flash-attn kernel still advertises MultipleOf(8)",
        )

    if not LAYOUT.is_file():
        rec("layout source", False, f"missing {LAYOUT}")
    else:
        layout_text = LAYOUT.read_text(encoding="utf-8")
        expected_src = {
            "LBHNC": "(0, 1, 2, 3, 4)",
            "LBNHC": "(0, 1, 3, 2, 4)",
            "LHBNC": "(0, 2, 1, 3, 4)",
            "BLHNC": "(1, 0, 2, 3, 4)",
            "BLNHC": "(1, 0, 3, 2, 4)",
            "BHLNC": "(1, 2, 0, 3, 4)",
        }
        for name, perm in expected_src.items():
            rec(
                f"layout {name}",
                f"{name} = {perm}" in layout_text,
                f"{name} physical stride is not {perm}",
            )

    return results


def main() -> int:
    failures = []
    for name, ok, reason in check_parity():
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
