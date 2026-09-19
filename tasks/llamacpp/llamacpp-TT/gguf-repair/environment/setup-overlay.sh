#!/bin/bash
# Write a GGUF shard that the ggml reader rejects.
set -euo pipefail

mkdir -p /data
python3 - <<'PY'
import math
import struct
from pathlib import Path

# GGUF v3 little-endian writer with intentional defects.
GGUF_MAGIC = b"GGUF"
VERSION = 3
ALIGN = 32

UINT8, INT8, UINT16, INT16, UINT32, INT32, FLOAT32, BOOL, STRING, ARRAY, UINT64, INT64, FLOAT64 = range(13)
GGML_F32 = 0
GGML_Q8_0 = 8


def pack_str(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("<Q", len(b)) + b


def pack_kv(key: str, typ: int, payload: bytes) -> bytes:
    return pack_str(key) + struct.pack("<i", typ) + payload


kvs = []
# Duplicate general.name: first "shard-a", second "shard-b". Reader rejects duplicates.
kvs.append(pack_kv("general.architecture", STRING, pack_str("llama")))
kvs.append(pack_kv("general.name", STRING, pack_str("shard-a")))
kvs.append(pack_kv("general.name", STRING, pack_str("shard-b")))
# Wrong type for alignment (FLOAT32 instead of UINT32).
kvs.append(pack_kv("general.alignment", FLOAT32, struct.pack("<f", 32.0)))
kvs.append(pack_kv("some.parameter.uint8", UINT8, struct.pack("<B", 0x12)))
kvs.append(pack_kv("some.parameter.int32", INT32, struct.pack("<i", -99)))
kvs.append(pack_kv("some.parameter.bool", BOOL, struct.pack("<b", 1)))
arr = struct.pack("<i", INT16) + struct.pack("<Q", 4) + struct.pack("<hhhh", 1, 2, 3, 4)
kvs.append(pack_kv("some.parameter.arr.i16", ARRAY, arr))
kvs.append(pack_kv("some.parameter.string", STRING, pack_str("hello world")))

# Two F32 tensors with distinctive payloads.
def f32_payload(n, start):
    return b"".join(struct.pack("<f", float(start + i) * 0.125) for i in range(n))

# ne = [n0, n1, n2, n3], n_dims=2
t1_ne = (8, 4, 1, 1)
t1_n_dims = 2
t1_data = f32_payload(8 * 4, 10)

t2_ne = (4, 3, 2, 1)
t2_n_dims = 3
t2_data = f32_payload(4 * 3 * 2, 100)

tensors_meta = []
offset = 0

def add_tensor(name, n_dims, ne, ggml_type, data):
    global offset
    info = pack_str(name)
    info += struct.pack("<I", n_dims)
    info += struct.pack("<" + "q" * 4, *ne)
    info += struct.pack("<i", ggml_type)
    info += struct.pack("<Q", offset)
    tensors_meta.append(info)
    # pad each tensor to ALIGN in the data blob
    pad = (ALIGN - (len(data) % ALIGN)) % ALIGN
    blob = data + (b"\x00" * pad)
    offset += len(blob)
    return blob

data_blob = b""
data_blob += add_tensor("blk.0.attn_q.weight", t1_n_dims, t1_ne, GGML_F32, t1_data)
data_blob += add_tensor("blk.0.ffn_down.weight", t2_n_dims, t2_ne, GGML_F32, t2_data)

kv_blob = b"".join(kvs)
header = GGUF_MAGIC + struct.pack("<I", VERSION)
header += struct.pack("<q", 2)  # n_tensors
header += struct.pack("<q", len(kvs))  # n_kv including duplicate
ti_blob = b"".join(tensors_meta)

pre = header + kv_blob + ti_blob
pad0 = (ALIGN - (len(pre) % ALIGN)) % ALIGN
# Defect: omit the alignment padding before the data blob (pad with 7 bytes instead).
broken_pad = b"\xaa" * 7

out = pre + broken_pad + data_blob
Path("/data/shard.gguf").write_bytes(out)
print("wrote /data/shard.gguf", len(out), "bytes")
PY

chmod a+r /data/shard.gguf
exit 0
