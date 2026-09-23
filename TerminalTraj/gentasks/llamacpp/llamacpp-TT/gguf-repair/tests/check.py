#!/usr/bin/env python3
"""Independent verifier for the GGUF shard repair task."""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/tests")
from ggufutil import (  # noqa: E402
    GGUFError,
    TYPE_NAMES,
    GGML_TYPE_NAMES,
    parse_gguf,
    pack_kv,
    pack_str,
    write_simple_f32_gguf,
)

SHARD_GOLDEN = Path("/tests/fixtures/shard.gguf")
DATA_SHARD = Path("/data/shard.gguf")
REPAIRED = Path("/results/repaired.gguf")
INVENTORY = Path("/results/inventory.json")
INV_GOLDEN = Path("/tests/goldens/inventory.json")
T1_GOLDEN = Path("/tests/goldens/t1.bin")
T2_GOLDEN = Path("/tests/goldens/t2.bin")
CLI = Path("/results/bin/gguf-audit")

INV_KEYS = ["version", "alignment", "n_kv", "n_tensors", "kv", "tensors"]
KV_KEYS = ["key", "type"]
TENSOR_KEYS = ["name", "n_dims", "ne", "type", "nbytes", "offset"]
KV_TYPES = {
    "UINT8", "INT8", "UINT16", "INT16", "UINT32", "INT32", "FLOAT32",
    "BOOL", "STRING", "ARRAY", "UINT64", "INT64", "FLOAT64",
}


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def top_keys(text: str) -> list:
    return list(json.loads(text).keys())


def check_data_unmodified() -> None:
    if not DATA_SHARD.is_file():
        fail("missing /data/shard.gguf (must not be deleted)")
    if sha256(DATA_SHARD) != sha256(SHARD_GOLDEN):
        fail("/data/shard.gguf was modified; fixture is read-only")


def check_inventory_text(text: str, parsed) -> dict:
    if not text.endswith("\n"):
        fail("inventory.json must end with a newline")
    try:
        inv = json.loads(text)
    except json.JSONDecodeError as e:
        fail(f"inventory.json is not valid JSON: {e}")
    if not isinstance(inv, dict):
        fail("inventory.json must be a JSON object")
    if top_keys(text) != INV_KEYS:
        fail(f"inventory.json keys must be {INV_KEYS} in that order, got {top_keys(text)}")
    for k in ("version", "alignment", "n_kv", "n_tensors"):
        if not isinstance(inv[k], int) or isinstance(inv[k], bool):
            fail(f"inventory.json {k} must be an integer")
    if inv["version"] != 3:
        fail(f"inventory version {inv['version']} != 3")
    if inv["alignment"] != 32:
        fail(f"inventory alignment {inv['alignment']} != 32")
    if inv["n_kv"] != len(inv["kv"]) or inv["n_tensors"] != len(inv["tensors"]):
        fail("n_kv / n_tensors do not match array lengths")
    if not isinstance(inv["kv"], list) or not isinstance(inv["tensors"], list):
        fail("kv and tensors must be arrays")
    for i, item in enumerate(inv["kv"]):
        if list(item.keys()) != KV_KEYS:
            fail(f"kv[{i}] keys must be {KV_KEYS} in that order")
        if item["type"] not in KV_TYPES:
            fail(f"kv[{i}] type {item['type']!r} is not a listed GGUF type name")
    for i, item in enumerate(inv["tensors"]):
        if list(item.keys()) != TENSOR_KEYS:
            fail(f"tensors[{i}] keys must be {TENSOR_KEYS} in that order")
        if not isinstance(item["ne"], list) or len(item["ne"]) != 4:
            fail(f"tensors[{i}].ne must be an array of exactly 4 ints")
        if any(not isinstance(x, int) or isinstance(x, bool) for x in item["ne"]):
            fail(f"tensors[{i}].ne must be ints")
        if item["type"] != item["type"].upper() or item["type"] != GGML_TYPE_NAMES.get(
            next((t.ggml_type for t in parsed.tensors if t.name == item["name"]), -1), item["type"]
        ):
            # uppercase ggml type name, not ggml_type_name ("f32")
            if item["type"] != item["type"].upper() or item["type"] == item["type"].lower():
                fail(f"tensors[{i}].type must be uppercase ggml type, got {item['type']!r}")
        if item["type"] == "f32" or item["type"] == "f16":
            fail(f"tensors[{i}].type looks like ggml_type_name, want uppercase F32/Q8_0")
    return inv


def run_audit(path: Path) -> dict:
    if not CLI.is_file() or not os.access(CLI, os.X_OK):
        fail("/results/bin/gguf-audit must be an executable file")
    proc = subprocess.run(
        [str(CLI), str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        fail(
            f"gguf-audit {path} exited {proc.returncode}\n"
            f"stdout: {proc.stdout[:500]!r}\nstderr: {proc.stderr[:800]!r}"
        )
    try:
        text = proc.stdout.decode("utf-8")
        obj = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        fail(f"gguf-audit stdout is not JSON: {e}; got {proc.stdout[:300]!r}")
    return obj


def main() -> None:
    check_data_unmodified()
    if not REPAIRED.is_file() or REPAIRED.stat().st_size == 0:
        fail("missing or empty /results/repaired.gguf")
    if not INVENTORY.is_file():
        fail("missing /results/inventory.json")
    raw = REPAIRED.read_bytes()
    if raw[:4] != b"GGUF":
        fail(f"repaired.gguf magic {raw[:4]!r} != b'GGUF'")
    try:
        parsed = parse_gguf(raw)
    except GGUFError as e:
        fail(f"repaired.gguf is not a well-formed GGUF v3 file: {e}")
    if parsed.version != 3:
        fail(f"repaired.gguf version {parsed.version} != 3")
    if parsed.alignment != 32:
        fail(f"repaired.gguf alignment {parsed.alignment} != 32")
    if parsed.data_offset % 32 != 0:
        fail(f"tensor data blob start {parsed.data_offset} is not aligned to 32")
    pad = raw[parsed.data_offset - ((32 - (parsed.data_offset % 32)) % 32) : parsed.data_offset]
    # padding bytes immediately before the data blob must be zeros
    header_end_guess = parsed.data_offset
    # verify zero padding in [unpadded_end, data_offset)
    # We recompute unpadded header length by parsing without consuming pad:
    # data_offset already includes pad; bytes in the pad window must be 0.
    # Find last non-header by checking pad region length.
    # Pad region is data_offset - ((data_offset % 32) would be 0). Reconstruct:
    # The pad is the bytes after tensor info up to data_offset; those must be 0x00 not 0xaa.
    if b"\xaa" in raw[parsed.data_offset - 32 : parsed.data_offset] and parsed.data_offset >= 32:
        # original defect used 0xaa padding; repaired file must use zero pad
        window = raw[max(0, parsed.data_offset - 32) : parsed.data_offset]
        if window.count(b"\xaa") >= 7 and all(b == 0xAA for b in window[-7:]):
            fail("repaired.gguf still has the defective 0xaa padding before the data blob")

    keys = [k for k, _t, _v in parsed.kv]
    if len(keys) != len(set(keys)):
        fail("repaired.gguf still contains duplicate KV keys")
    kv_map = {k: (t, v) for k, t, v in parsed.kv}
    if "general.alignment" not in kv_map:
        fail("missing general.alignment")
    atyp, aval = kv_map["general.alignment"]
    if atyp != 4 or int(aval) != 32:
        fail(f"general.alignment must be UINT32 32, got type={atyp} value={aval!r}")
    if kv_map.get("general.name", (None, None))[1] != "shard-a":
        fail(f"duplicate general.name must keep the first value 'shard-a', got {kv_map.get('general.name')}")
    if kv_map.get("general.architecture", (None, None))[1] != "llama":
        fail("general.architecture must remain 'llama'")
    expected_kv_order = [
        "general.architecture",
        "general.name",
        "general.alignment",
        "some.parameter.uint8",
        "some.parameter.int32",
        "some.parameter.bool",
        "some.parameter.arr.i16",
        "some.parameter.string",
    ]
    if keys != expected_kv_order:
        fail(f"KV key order {keys} != {expected_kv_order} (drop duplicate, keep first)")
    u8_t, u8_v = kv_map["some.parameter.uint8"]
    if u8_t != 0 or int(u8_v) != 0x12:
        fail("some.parameter.uint8 not preserved")
    i32_t, i32_v = kv_map["some.parameter.int32"]
    if i32_t != 5 or int(i32_v) != -99:
        fail("some.parameter.int32 not preserved")
    b_t, b_v = kv_map["some.parameter.bool"]
    if b_t != 7 or b_v is not True:
        fail("some.parameter.bool not preserved")
    arr_t, arr_v = kv_map["some.parameter.arr.i16"]
    if arr_t != 9 or arr_v[0] != "ARRAY" or arr_v[1] != 3 or list(arr_v[2]) != [1, 2, 3, 4]:
        fail(f"some.parameter.arr.i16 not preserved: {arr_v!r}")
    s_t, s_v = kv_map["some.parameter.string"]
    if s_t != 8 or s_v != "hello world":
        fail("some.parameter.string not preserved")

    if len(parsed.tensors) != 2:
        fail(f"expected 2 tensors, got {len(parsed.tensors)}")
    t1, t2 = parsed.tensors
    if t1.name != "blk.0.attn_q.weight" or t1.n_dims != 2 or t1.ne != [8, 4, 1, 1] or t1.ggml_type != 0:
        fail(f"tensor 0 metadata mismatch: {t1}")
    if t2.name != "blk.0.ffn_down.weight" or t2.n_dims != 3 or t2.ne != [4, 3, 2, 1] or t2.ggml_type != 0:
        fail(f"tensor 1 metadata mismatch: {t2}")
    if t1.nbytes != 128 or t2.nbytes != 96:
        fail(f"unpadded nbytes {t1.nbytes},{t2.nbytes} != 128,96")
    if t1.offset % 32 != 0 or t2.offset % 32 != 0:
        fail("tensor offsets are not aligned to 32")
    if t1.offset != 0:
        fail(f"first tensor offset {t1.offset} != 0")
    # second tensor follows the first payload padded to alignment
    padded_t1 = t1.nbytes + ((32 - (t1.nbytes % 32)) % 32)
    if t2.offset != padded_t1:
        fail(f"second tensor offset {t2.offset} != padded first size {padded_t1}")

    blob = parsed.data
    got1 = blob[t1.offset : t1.offset + t1.nbytes]
    got2 = blob[t2.offset : t2.offset + t2.nbytes]
    if got1 != T1_GOLDEN.read_bytes():
        fail("blk.0.attn_q.weight payload bytes were not preserved")
    if got2 != T2_GOLDEN.read_bytes():
        fail("blk.0.ffn_down.weight payload bytes were not preserved")
    # padding after each tensor inside the data blob must be zeros
    pad1 = blob[t1.offset + t1.nbytes : t2.offset]
    if pad1 != b"\x00" * len(pad1):
        fail("non-zero padding between tensors")

    inv_text = INVENTORY.read_text(encoding="utf-8")
    inv = check_inventory_text(inv_text, parsed)
    gold = json.loads(INV_GOLDEN.read_text(encoding="utf-8"))
    if inv != gold:
        fail(f"inventory.json does not match independent golden\n got {inv}\n want {gold}")

    # behavior: CLI reproduces the inventory from the repaired path
    audit = run_audit(REPAIRED)
    if audit != gold:
        fail(f"gguf-audit /results/repaired.gguf does not match inventory.json / golden")

    # behavior: CLI works on an arbitrary well-formed GGUF, not a hardcoded dump
    with tempfile.TemporaryDirectory(prefix="gguf-cli-") as td:
        td_path = Path(td)
        alt = td_path / "alt.gguf"
        payload = b"".join(struct.pack("<f", float(i)) for i in range(8))
        kvs = [
            pack_kv("general.architecture", 8, pack_str("llama")),
            pack_kv("general.alignment", 4, struct.pack("<I", 32)),
            pack_kv("probe.name", 8, pack_str("alt-shard")),
        ]
        write_simple_f32_gguf(alt, kvs, [("probe.weight", 1, [8, 1, 1, 1], payload)])
        alt_audit = run_audit(alt)
        names = [t["name"] for t in alt_audit.get("tensors", [])]
        keys_out = [k["key"] for k in alt_audit.get("kv", [])]
        if "probe.weight" not in names:
            fail("gguf-audit ignored the alternate GGUF path (missing probe.weight)")
        if "probe.name" not in keys_out:
            fail("gguf-audit ignored the alternate GGUF path (missing probe.name)")
        if alt_audit.get("n_tensors") != 1 or alt_audit.get("alignment") != 32:
            fail(f"gguf-audit mis-reported the alternate file: {alt_audit}")

    print("c2 checks passed", file=sys.stderr)


if __name__ == "__main__":
    main()
