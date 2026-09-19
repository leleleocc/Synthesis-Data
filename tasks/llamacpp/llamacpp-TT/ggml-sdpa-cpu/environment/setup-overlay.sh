#!/bin/bash
# Install the CPU attention fixture under /data.
set -euo pipefail

mkdir -p /data
python3 - <<'PY'
import json
from pathlib import Path

n_head = 2
n_embd_head = 8
n_token = 4
eps = 1.0e-5
rope_freq_base = 10000.0

def cell(kind, t, h, d):
    # Deterministic, non-trivial values (not a single scale).
    base = 0.15 * (t + 1) + 0.07 * h + 0.03 * (d + 1)
    if kind == "q":
        return round(base * 0.5 - 0.25, 6)
    if kind == "k":
        return round(0.4 * ((d % 3) - 1) + 0.05 * t - 0.02 * h, 6)
    return round(0.2 * ((h + 1) / (d + 2)) - 0.1 * t, 6)

q = [[[cell("q", t, h, d) for d in range(n_embd_head)] for h in range(n_head)] for t in range(n_token)]
k = [[[cell("k", t, h, d) for d in range(n_embd_head)] for h in range(n_head)] for t in range(n_token)]
v = [[[cell("v", t, h, d) for d in range(n_embd_head)] for h in range(n_head)] for t in range(n_token)]
pos = [0, 1, 2, 3]

doc = {
    "n_head": n_head,
    "n_embd_head": n_embd_head,
    "n_token": n_token,
    "eps": eps,
    "rope_freq_base": rope_freq_base,
    "q": q,
    "k": k,
    "v": v,
    "pos": pos,
}
Path("/data/attn_fixture.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
PY

chmod a+r /data/attn_fixture.json
exit 0
