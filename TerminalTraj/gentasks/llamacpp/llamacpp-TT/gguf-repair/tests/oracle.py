#!/usr/bin/env python3
"""Independent GGUF inventory / payload oracle for c2."""
from __future__ import annotations

import json
import os
import struct
import sys
from collections import OrderedDict
from pathlib import Path

GGUF_MAGIC = b"GGUF"
ALIGN = 32
UINT8, INT8, UINT16, INT16, UINT32, INT32, FLOAT32, BOOL, STRING, ARRAY, UINT64, INT64, FLOAT64 = range(13)

KV_TYPE_NAMES = {
    UINT8: "UINT8",
    INT8: "INT8",
    UINT16: "UINT16",
    INT16: "INT16",
    UINT32: "UINT32",
    INT32: "INT32",
    FLOAT32: "FLOAT32",
    BOOL: "BOOL",
    STRING: "STRING",
    ARRAY: "ARRAY",
    UINT64: "UINT64",
    INT64: "INT64",
    FLOAT64: "FLOAT64",
}

GGML_TYPE_UPPER = {
    0: "F32",
    1: "F16",
    2: "Q4_0",
    3: "Q4_1",
    6: "Q5_0",
    7: "Q5_1",
    8: "Q8_0",
    9: "Q8_1",
    10: "Q2_K",
    11: "Q3_K",
    12: "Q4_K",
    13: "Q5_K",
    14: "Q6_K",
}

SCALAR_SIZE = {
    UINT8: 1,
    INT8: 1,
    UINT16: 2,
    INT16: 2,
    UINT32: 4,
    INT32: 4,
    FLOAT32: 4,
    BOOL: 1,
    UINT64: 8,
    INT64: 8,
    FLOAT64: 8,
}

GGML_TYPE_SIZE = {
    0: (1, 4),  # F32: blck, type_size
}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.off = 0

    def remaining(self) -> int:
        return len(self.data) - self.off

    def take(self, n: int) -> bytes:
        if self.off + n > len(self.data):
            fail(f"truncated GGUF at offset {self.off}, need {n}")
        chunk = self.data[self.off : self.off + n]
        self.off += n
        return chunk

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.take(8))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def string(self) -> str:
        n = self.u64()
        return self.take(n).decode("utf-8")


def skip_value(r: Reader, typ: int) -> None:
    if typ == STRING:
        n = r.u64()
        r.take(n)
        return
    if typ == ARRAY:
        et = r.i32()
        n = r.u64()
        if et == STRING:
            for _ in range(n):
                slen = r.u64()
                r.take(slen)
        else:
            if et not in SCALAR_SIZE:
                fail(f"unsupported array element type {et}")
            r.take(SCALAR_SIZE[et] * n)
        return
    if typ not in SCALAR_SIZE:
        fail(f"unsupported kv type {typ}")
    r.take(SCALAR_SIZE[typ])


def parse_gguf(path: str):
    data = Path(path).read_bytes()
    r = Reader(data)
    magic = r.take(4)
    if magic != GGUF_MAGIC:
        fail(f"{path} magic {magic!r} != GGUF")
    version = r.u32()
    n_tensors = r.i64()
    n_kv = r.i64()
    kv = []
    seen = set()
    alignment_value = None
    for _ in range(n_kv):
        key = r.string()
        typ = r.i32()
        if typ not in KV_TYPE_NAMES:
            fail(f"unknown kv type {typ} for {key}")
        if key == "general.alignment":
            if typ != UINT32:
                fail("general.alignment must be stored as UINT32")
            alignment_value = struct.unpack("<I", r.take(4))[0]
            if alignment_value != ALIGN:
                fail(f"general.alignment value {alignment_value} != {ALIGN}")
        else:
            skip_value(r, typ)
        kv.append({"key": key, "type": KV_TYPE_NAMES[typ]})
        if key in seen:
            fail(f"duplicate key still present: {key}")
        seen.add(key)
    if alignment_value is None:
        fail("repaired GGUF missing general.alignment")
    tensors = []
    for _ in range(n_tensors):
        name = r.string()
        n_dims = r.u32()
        if n_dims < 1 or n_dims > 4:
            fail(f"tensor {name} n_dims {n_dims} not in 1..4")
        # Spec: one int64 per dimension; unused dims in the inventory are 1.
        ne = [1, 1, 1, 1]
        for d in range(n_dims):
            ne[d] = r.i64()
        ggml_type = r.i32()
        offset = r.u64()
        n_elem = 1
        for d in range(n_dims):
            n_elem *= ne[d]
        if ggml_type == 0:
            nbytes = n_elem * 4
        else:
            fail(f"unexpected ggml type {ggml_type} for {name}")
        tensors.append(
            {
                "name": name,
                "n_dims": n_dims,
                "ne": ne,
                "type": GGML_TYPE_UPPER.get(ggml_type, f"TYPE_{ggml_type}"),
                "nbytes": nbytes,
                "offset": offset,
                "ggml_type": ggml_type,
            }
        )
    pad = (ALIGN - (r.off % ALIGN)) % ALIGN
    if pad:
        padding = r.take(pad)
        if padding != b"\x00" * pad:
            fail("alignment padding before tensor blob is not zero")
    data_off = r.off
    for t in tensors:
        if t["offset"] % ALIGN != 0:
            fail(f"tensor {t['name']} offset {t['offset']} not aligned to {ALIGN}")
        start = data_off + t["offset"]
        end = start + t["nbytes"]
        if end > len(data):
            fail(f"tensor {t['name']} payload overruns file")
        t["payload"] = data[start:end]
    return {
        "version": version,
        "alignment": ALIGN,
        "n_kv": n_kv,
        "n_tensors": n_tensors,
        "kv": kv,
        "tensors": tensors,
        "data_off": data_off,
        "raw": data,
    }


def expected_from_broken(path: str):
    """Best-effort reconstruction of original payloads from the overlay fixture."""
    data = Path(path).read_bytes()
    # Overlay writes two F32 tensors with known generation formula.
    def f32_payload(n, start):
        return b"".join(struct.pack("<f", float(start + i) * 0.125) for i in range(n))

    t1 = f32_payload(8 * 4, 10)
    t2 = f32_payload(4 * 3 * 2, 100)
    kv = [
        {"key": "general.architecture", "type": "STRING"},
        {"key": "general.name", "type": "STRING"},
        {"key": "general.alignment", "type": "UINT32"},
        {"key": "some.parameter.uint8", "type": "UINT8"},
        {"key": "some.parameter.int32", "type": "INT32"},
        {"key": "some.parameter.bool", "type": "BOOL"},
        {"key": "some.parameter.arr.i16", "type": "ARRAY"},
        {"key": "some.parameter.string", "type": "STRING"},
    ]
    tensors = [
        {
            "name": "blk.0.attn_q.weight",
            "n_dims": 2,
            "ne": [8, 4, 1, 1],
            "type": "F32",
            "nbytes": len(t1),
            "payload": t1,
        },
        {
            "name": "blk.0.ffn_down.weight",
            "n_dims": 3,
            "ne": [4, 3, 2, 1],
            "type": "F32",
            "nbytes": len(t2),
            "payload": t2,
        },
    ]
    return {"kv": kv, "tensors": tensors, "n_kv": len(kv), "n_tensors": 2, "version": 3, "alignment": 32}


def load_ordered(path: str):
    text = Path(path).read_bytes()
    if not text.endswith(b"\n"):
        fail(f"{path} must end with a newline")
    decoder = json.JSONDecoder(object_pairs_hook=OrderedDict)
    obj, idx = decoder.raw_decode(text.decode("utf-8"))
    rest = text.decode("utf-8")[idx:]
    if rest.strip() != "":
        fail(f"{path} has trailing junk")
    return obj


def check_inventory(inv, parsed, expected):
    keys = list(inv.keys())
    want_keys = ["version", "alignment", "n_kv", "n_tensors", "kv", "tensors"]
    if keys != want_keys:
        fail(f"inventory.json keys {keys} != {want_keys}")
    for k in ("version", "alignment", "n_kv", "n_tensors"):
        if not isinstance(inv[k], int) or isinstance(inv[k], bool):
            fail(f"{k} must be a JSON integer")
    if inv["version"] != 3:
        fail(f"version {inv['version']} != 3")
    if inv["alignment"] != 32:
        fail(f"alignment {inv['alignment']} != 32")
    if inv["n_kv"] != expected["n_kv"] or inv["n_kv"] != parsed["n_kv"]:
        fail(f"n_kv mismatch inventory={inv['n_kv']} file={parsed['n_kv']}")
    if inv["n_tensors"] != expected["n_tensors"]:
        fail("n_tensors mismatch")
    if not isinstance(inv["kv"], list) or len(inv["kv"]) != expected["n_kv"]:
        fail("kv array length mismatch")
    for i, (got, want) in enumerate(zip(inv["kv"], expected["kv"])):
        if list(got.keys()) != ["key", "type"]:
            fail(f"kv[{i}] keys {list(got.keys())} != ['key','type']")
        if got["key"] != want["key"] or got["type"] != want["type"]:
            fail(f"kv[{i}] {got} != {want}")
    if not isinstance(inv["tensors"], list) or len(inv["tensors"]) != expected["n_tensors"]:
        fail("tensors array length mismatch")
    for i, (got, want, file_t) in enumerate(zip(inv["tensors"], expected["tensors"], parsed["tensors"])):
        if list(got.keys()) != ["name", "n_dims", "ne", "type", "nbytes", "offset"]:
            fail(f"tensors[{i}] keys {list(got.keys())}")
        if got["name"] != want["name"]:
            fail(f"tensor name {got['name']} != {want['name']}")
        if got["n_dims"] != want["n_dims"]:
            fail(f"n_dims mismatch for {got['name']}")
        if not isinstance(got["ne"], list) or len(got["ne"]) != 4:
            fail("ne must be length 4")
        if got["ne"] != want["ne"]:
            fail(f"ne mismatch for {got['name']}: {got['ne']} != {want['ne']}")
        if got["type"] != want["type"]:
            fail(f"type {got['type']} != {want['type']} (uppercase ggml name required)")
        if got["nbytes"] != want["nbytes"]:
            fail(f"nbytes {got['nbytes']} != {want['nbytes']}")
        if got["offset"] != file_t["offset"]:
            fail(f"offset mismatch for {got['name']}")
        if file_t["payload"] != want["payload"]:
            fail(f"payload bytes changed for {got['name']}")


def main() -> None:
    repaired = os.environ.get("C2_REPAIRED", "/results/repaired.gguf")
    inventory = os.environ.get("C2_INVENTORY", "/results/inventory.json")
    broken = os.environ.get("C2_BROKEN", "/data/shard.gguf")
    if not Path(repaired).is_file():
        fail(f"missing {repaired}")
    if not Path(inventory).is_file():
        fail(f"missing {inventory}")
    if not Path(broken).is_file():
        fail(f"missing {broken}")
    expected = expected_from_broken(broken)
    parsed = parse_gguf(repaired)
    if parsed["version"] != 3:
        fail("repaired GGUF version is not 3")
    if parsed["n_kv"] != expected["n_kv"]:
        fail("repaired GGUF n_kv is not the de-duplicated count")
    inv = load_ordered(inventory)
    check_inventory(inv, parsed, expected)
    print("oracle: repaired GGUF inventory and payloads match")


if __name__ == "__main__":
    main()
