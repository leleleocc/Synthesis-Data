#!/usr/bin/env python3
"""Independent ggml-style quant size / Q8_0 RMSE oracle for c5."""
from __future__ import annotations

import json
import math
import os
import re
import struct
import sys
from collections import OrderedDict
from pathlib import Path

QK4_0 = 32
QK5_0 = 32
QK8_0 = 32
QK_K = 256
K_SCALE_SIZE = 12

# type_size from ggml-common.h static_assert layouts
TYPE_SIZE = {
    "Q8_0": 2 + QK8_0,                 # half + 32 int8
    "Q4_0": 2 + QK4_0 // 2,            # half + 16 nibbles
    "Q5_0": 2 + 4 + QK5_0 // 2,        # half + uint32 qh + 16 nibbles
    "Q4_K": 2 * 2 + K_SCALE_SIZE + QK_K // 2,  # 2 half + 12 scales + 128 qs
}
BLCK = {
    "Q8_0": QK8_0,
    "Q4_0": QK4_0,
    "Q5_0": QK5_0,
    "Q4_K": QK_K,
}
TYPE_ORDER = ["Q8_0", "Q4_0", "Q5_0", "Q4_K"]
TYPE_FILE = {"Q8_0": "q8_0", "Q4_0": "q4_0", "Q5_0": "q5_0", "Q4_K": "q4_k"}
REQUIRES_IMATRIX = {"Q8_0": False, "Q4_0": False, "Q5_0": False, "Q4_K": False}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def fp16_from_f32(x: float) -> float:
    return struct.unpack("<e", struct.pack("<e", x))[0]


def quantize_q8_0(x):
    """Reference quantize_row_q8_0_ref + dequantize."""
    k = len(x)
    assert k % QK8_0 == 0
    packed = bytearray()
    xhat = [0.0] * k
    for i in range(k // QK8_0):
        block = x[i * QK8_0 : (i + 1) * QK8_0]
        amax = max(abs(v) for v in block)
        d = amax / 127.0
        id_ = (1.0 / d) if d else 0.0
        d_h = fp16_from_f32(d)
        packed += struct.pack("<e", d)
        qs = []
        for v in block:
            q = int(round(v * id_))
            q = max(-128, min(127, q))
            qs.append(q)
        packed += struct.pack("<" + "b" * QK8_0, *qs)
        for j, q in enumerate(qs):
            xhat[i * QK8_0 + j] = d_h * q
    return bytes(packed), xhat


def row_size(typ: str, ne0: int) -> int:
    blck = BLCK[typ]
    tsz = TYPE_SIZE[typ]
    if ne0 % blck != 0:
        fail(f"ne[0]={ne0} not divisible by block size {blck} for {typ}")
    return (ne0 // blck) * tsz


def load_tensor(stem: str, root: Path):
    f32 = (root / f"{stem}.f32").read_bytes()
    ne = [int(line) for line in (root / f"{stem}.shape").read_text(encoding="utf-8").splitlines() if line.strip() != ""]
    n_elem = 1
    for x in ne:
        n_elem *= x
    if len(f32) != n_elem * 4:
        fail(f"{stem}.f32 size {len(f32)} != {n_elem * 4}")
    vals = list(struct.unpack("<" + "f" * n_elem, f32))
    ne4 = list(ne) + [1] * (4 - len(ne))
    return ne4, n_elem, vals


def ten_decimals(raw: str, value_str_pattern=None) -> None:
    # Each rmse number must have exactly 10 digits after the decimal in the file.
    matches = re.findall(r'"rmse"\s*:\s*(-?\d+\.\d+)', raw)
    if not matches:
        fail("quant_audit.json missing rmse numbers")
    for m in matches:
        frac = m.split(".", 1)[1]
        if len(frac) != 10:
            fail(f"rmse must have exactly 10 digits after the decimal, got {m!r}")


def main() -> None:
    tensors_dir = Path(os.environ.get("C5_TENSORS", "/data/tensors"))
    packed_dir = Path(os.environ.get("C5_PACKED", "/results/packed"))
    report_path = Path(os.environ.get("C5_JSON", "/results/quant_audit.json"))
    if not tensors_dir.is_dir():
        fail("missing /data/tensors")
    if not packed_dir.is_dir():
        fail("missing /results/packed")
    if not report_path.is_file():
        fail("missing /results/quant_audit.json")

    stems = sorted(p.stem for p in tensors_dir.glob("*.f32"))
    if not stems:
        fail("no *.f32 tensors")

    raw_b = report_path.read_bytes()
    if not raw_b.endswith(b"\n"):
        fail("quant_audit.json must end with a newline")
    raw = raw_b.decode("utf-8")
    decoder = json.JSONDecoder(object_pairs_hook=OrderedDict)
    doc, idx = decoder.raw_decode(raw)
    if raw[idx:].strip() != "":
        fail("quant_audit.json has trailing junk")
    if list(doc.keys()) != ["tensors"]:
        fail(f"quant_audit.json keys {list(doc.keys())} != ['tensors']")
    if not isinstance(doc["tensors"], list):
        fail("tensors must be an array")
    got_stems = [t.get("stem") for t in doc["tensors"]]
    if got_stems != stems:
        fail(f"tensors not sorted by stem: {got_stems} vs {stems}")

    ten_decimals(raw)

    for entry, stem in zip(doc["tensors"], stems):
        if list(entry.keys()) != ["stem", "ne", "n_elem", "types"]:
            fail(f"tensor object keys {list(entry.keys())}")
        ne4, n_elem, vals = load_tensor(stem, tensors_dir)
        if entry["stem"] != stem:
            fail("stem mismatch")
        if entry["ne"] != ne4:
            fail(f"{stem} ne {entry['ne']} != {ne4}")
        if entry["n_elem"] != n_elem:
            fail(f"{stem} n_elem {entry['n_elem']} != {n_elem}")
        if not isinstance(entry["types"], list) or [t.get("type") for t in entry["types"]] != TYPE_ORDER:
            fail(f"{stem} types order != {TYPE_ORDER}")
        for tentry, typ in zip(entry["types"], TYPE_ORDER):
            if list(tentry.keys()) != ["type", "nbytes", "nbytes_expected", "rmse", "requires_imatrix"]:
                fail(f"type object keys {list(tentry.keys())}")
            if tentry["type"] != typ:
                fail(f"type {tentry['type']} != {typ}")
            expected = row_size(typ, ne4[0]) * (n_elem // ne4[0])
            if tentry["nbytes_expected"] != expected:
                fail(f"{stem}.{typ} nbytes_expected {tentry['nbytes_expected']} != {expected}")
            if tentry["nbytes"] != expected:
                fail(f"{stem}.{typ} nbytes {tentry['nbytes']} != packed size {expected}")
            if tentry["requires_imatrix"] is not False:
                fail(f"{stem}.{typ} requires_imatrix must be false")
            pfile = packed_dir / f"{stem}.{TYPE_FILE[typ]}"
            if not pfile.is_file():
                fail(f"missing packed file {pfile}")
            blob = pfile.read_bytes()
            if len(blob) != expected:
                fail(f"{pfile} size {len(blob)} != {expected}")
            if not isinstance(tentry["rmse"], (int, float)) or isinstance(tentry["rmse"], bool):
                fail("rmse must be a JSON number")
            if typ == "Q8_0":
                packed, xhat = quantize_q8_0(vals)
                if blob != packed:
                    # Some ggml builds may use a slightly different q8_0 path;
                    # still require RMSE to match the dequant of the packed bytes.
                    pass
                # RMSE vs original using dequant of reported packed bytes.
                # Decode packed q8_0 independently.
                xhat2 = []
                off = 0
                for i in range(n_elem // QK8_0):
                    d = struct.unpack_from("<e", blob, off)[0]
                    off += 2
                    qs = struct.unpack_from("<" + "b" * QK8_0, blob, off)
                    off += QK8_0
                    for q in qs:
                        xhat2.append(d * q)
                mse = sum((a - b) ** 2 for a, b in zip(vals, xhat2)) / n_elem
                rmse = math.sqrt(mse)
                if abs(float(tentry["rmse"]) - rmse) > 1e-6:
                    fail(f"{stem}.Q8_0 rmse {tentry['rmse']} != {rmse:.10f}")
            else:
                # Non-Q8 types: RMSE must be finite, non-negative, and not a
                # degenerate 0.0 unless the tensor is all zeros (it is not).
                rmse = float(tentry["rmse"])
                if not math.isfinite(rmse) or rmse < 0:
                    fail(f"{stem}.{typ} rmse is not a finite non-negative number")
                if rmse == 0.0:
                    fail(f"{stem}.{typ} rmse is 0; packed bytes are unlikely a lossless identity")
                # Packed file must not be all zeros (would be a fake dump).
                if blob == b"\x00" * len(blob):
                    fail(f"{pfile} is all zeros")
    if not re.search(r'"requires_imatrix"\s*:\s*false', raw):
        fail("requires_imatrix must be JSON false")
    print("oracle: quant audit sizes and Q8_0 RMSE match")


if __name__ == "__main__":
    main()
