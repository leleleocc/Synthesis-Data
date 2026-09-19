#!/usr/bin/env python3
"""Independent CPU SDPA oracle for c1 (no ggml)."""
from __future__ import annotations

import json
import math
import os
import re
import struct
import sys
from collections import OrderedDict


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_ordered(path: str):
    text = open(path, "rb").read()
    if not text.endswith(b"\n"):
        fail(f"{path} must end with a newline")
    decoder = json.JSONDecoder(object_pairs_hook=OrderedDict)
    obj, idx = decoder.raw_decode(text.decode("utf-8"))
    rest = text.decode("utf-8")[idx:]
    if rest.strip() != "":
        fail(f"{path} has trailing non-whitespace after the JSON value")
    return obj, text.decode("utf-8")


def rms_norm_vec(vec, eps):
    acc = 0.0
    for x in vec:
        acc += x * x
    scale = 1.0 / math.sqrt(acc / len(vec) + eps)
    return [x * scale for x in vec]


def rope_normal(vec, pos, n_dims, freq_base, attn_factor=1.0):
    out = list(vec)
    theta_scale = freq_base ** (-2.0 / n_dims)
    theta = float(pos)
    for i0 in range(0, n_dims, 2):
        cos_t = math.cos(theta) * attn_factor
        sin_t = math.sin(theta) * attn_factor
        x0 = vec[i0]
        x1 = vec[i0 + 1]
        out[i0] = x0 * cos_t - x1 * sin_t
        out[i0 + 1] = x0 * sin_t + x1 * cos_t
        theta *= theta_scale
    return out


def softmax(xs):
    m = max(xs)
    if m == float("-inf"):
        return [0.0] * len(xs)
    exps = []
    total = 0.0
    for x in xs:
        if x == float("-inf"):
            exps.append(0.0)
        else:
            e = math.exp(x - m)
            exps.append(e)
            total += e
    if total == 0.0:
        return [0.0] * len(xs)
    return [e / total for e in exps]


def expected_from_fixture(doc):
    n_head = int(doc["n_head"])
    n_embd_head = int(doc["n_embd_head"])
    n_token = int(doc["n_token"])
    eps = float(doc["eps"])
    rope_freq_base = float(doc["rope_freq_base"])
    q = doc["q"]
    k = doc["k"]
    v = doc["v"]
    pos = [int(p) for p in doc["pos"]]
    scale = 1.0 / math.sqrt(n_embd_head)

    qn = [
        [rms_norm_vec(q[t][h], eps) for h in range(n_head)]
        for t in range(n_token)
    ]
    kn = [
        [rms_norm_vec(k[t][h], eps) for h in range(n_head)]
        for t in range(n_token)
    ]
    vn = [
        [rms_norm_vec(v[t][h], eps) for h in range(n_head)]
        for t in range(n_token)
    ]
    qr = [
        [rope_normal(qn[t][h], pos[t], n_embd_head, rope_freq_base) for h in range(n_head)]
        for t in range(n_token)
    ]
    kr = [
        [rope_normal(kn[t][h], pos[t], n_embd_head, rope_freq_base) for h in range(n_head)]
        for t in range(n_token)
    ]

    flat_qn = [x for t in qn for h in t for x in h]
    rms_q = math.sqrt(sum(x * x for x in flat_qn) / len(flat_qn))

    out = [[[0.0] * n_embd_head for _ in range(n_head)] for _ in range(n_token)]
    max_attn = float("-inf")
    for h in range(n_head):
        for t in range(n_token):
            scores = []
            for s in range(n_token):
                if pos[s] <= pos[t]:
                    dot = 0.0
                    for d in range(n_embd_head):
                        dot += qr[t][h][d] * kr[s][h][d]
                    scores.append(dot * scale)
                else:
                    scores.append(float("-inf"))
            attn = softmax(scores)
            max_attn = max(max_attn, max(attn))
            for d in range(n_embd_head):
                acc = 0.0
                for s in range(n_token):
                    acc += attn[s] * vn[s][h][d]
                out[t][h][d] = acc
    return {
        "n_head": n_head,
        "n_embd_head": n_embd_head,
        "n_token": n_token,
        "rms_q": rms_q,
        "max_attn": max_attn,
        "out": out,
    }


def eight_decimals(raw: str, key: str) -> None:
    m = re.search(r'"%s"\s*:\s*(-?\d+\.\d+)' % re.escape(key), raw)
    if not m:
        fail(f"attn_meta.json missing decimal number for {key}")
    frac = m.group(1).split(".", 1)[1]
    if len(frac) != 8:
        fail(f"{key} must have exactly 8 digits after the decimal, got {m.group(1)!r}")


def main() -> None:
    fixture_path = os.environ.get("C1_FIXTURE", "/data/attn_fixture.json")
    bin_path = os.environ.get("C1_BIN", "/results/attn_out.bin")
    meta_path = os.environ.get("C1_META", "/results/attn_meta.json")
    if not os.path.isfile(fixture_path):
        fail(f"missing fixture {fixture_path}")
    if not os.path.isfile(bin_path):
        fail(f"missing {bin_path}")
    if not os.path.isfile(meta_path):
        fail(f"missing {meta_path}")

    fixture = json.loads(open(fixture_path, encoding="utf-8").read())
    exp = expected_from_fixture(fixture)
    n_elem = exp["n_head"] * exp["n_embd_head"] * exp["n_token"]
    n_bytes = n_elem * 4

    blob = open(bin_path, "rb").read()
    if len(blob) != n_bytes:
        fail(f"attn_out.bin size {len(blob)} != {n_bytes}")
    got = list(struct.unpack("<" + "f" * n_elem, blob))
    want = [x for t in exp["out"] for h in t for x in h]
    max_abs = max(abs(a - b) for a, b in zip(got, want))
    if max_abs > 1e-4:
        fail(f"attn_out.bin max abs error {max_abs} exceeds 1e-4")

    meta, raw = load_ordered(meta_path)
    keys = list(meta.keys())
    expected_keys = ["n_head", "n_embd_head", "n_token", "n_bytes", "rms_q", "max_attn"]
    if keys != expected_keys:
        fail(f"attn_meta.json keys {keys} != {expected_keys}")
    for k in ("n_head", "n_embd_head", "n_token", "n_bytes"):
        if not isinstance(meta[k], int) or isinstance(meta[k], bool):
            fail(f"{k} must be a JSON integer")
    if meta["n_head"] != exp["n_head"] or meta["n_embd_head"] != exp["n_embd_head"]:
        fail("attn_meta.json shape fields do not match the fixture")
    if meta["n_token"] != exp["n_token"]:
        fail("attn_meta.json n_token does not match the fixture")
    if meta["n_bytes"] != n_bytes:
        fail(f"n_bytes {meta['n_bytes']} != {n_bytes}")
    if not isinstance(meta["rms_q"], (int, float)) or isinstance(meta["rms_q"], bool):
        fail("rms_q must be a JSON number")
    if not isinstance(meta["max_attn"], (int, float)) or isinstance(meta["max_attn"], bool):
        fail("max_attn must be a JSON number")
    eight_decimals(raw, "rms_q")
    eight_decimals(raw, "max_attn")
    if abs(float(meta["rms_q"]) - exp["rms_q"]) > 5e-7:
        fail(f"rms_q {meta['rms_q']} != {exp['rms_q']:.8f}")
    if abs(float(meta["max_attn"]) - exp["max_attn"]) > 5e-7:
        fail(f"max_attn {meta['max_attn']} != {exp['max_attn']:.8f}")
    print("oracle: attn outputs match")


if __name__ == "__main__":
    main()
