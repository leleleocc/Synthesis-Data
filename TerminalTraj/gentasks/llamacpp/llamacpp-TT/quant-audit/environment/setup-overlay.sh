#!/bin/bash
# Synthetic F32 tensors for ggml quant audit (ne[0] multiple of 256).
set -euo pipefail

mkdir -p /data/tensors
python3 - <<'PY'
import math
import struct
from pathlib import Path

root = Path("/data/tensors")


def write_tensor(stem, ne, amplitude=1.25, offset=0.17):
    # ne: ggml dims, ne[0] fastest. n_elem = product.
    n_elem = 1
    for x in ne:
        n_elem *= x
    data = []
    for i in range(n_elem):
        data.append(0.1 + amplitude * math.cos(i + offset))
    blob = b"".join(struct.pack("<f", float(v)) for v in data)
    (root / f"{stem}.f32").write_bytes(blob)
    (root / f"{stem}.shape").write_text("".join(f"{x}\n" for x in ne), encoding="utf-8")


# Q4_K / Q8_0 / Q4_0 / Q5_0 all require ne[0] % 256 == 0 (QK_K) and % 32 == 0.
write_tensor("attn_q", [256, 4], amplitude=2.0, offset=0.3)
write_tensor("ffn_down", [256, 2], amplitude=0.75, offset=1.1)
write_tensor("tok_embd", [256], amplitude=1.5, offset=2.2)
print("wrote tensors", list(p.name for p in sorted(root.iterdir())))
PY

chmod -R a+rX /data/tensors
exit 0
