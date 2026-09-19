#!/usr/bin/env python3
"""Independent verifier for the ggml CPU quant audit."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

FIX_DIR = Path("/tests/fixtures/tensors")
DATA_DIR = Path("/data/tensors")
PACKED = Path("/results/packed")
AUDIT = Path("/results/quant_audit.json")
GOLD_AUDIT = Path("/tests/goldens/quant_audit.json")
GOLD_PACKED = Path("/tests/goldens/packed")
CLI = Path("/results/bin/quant-audit")

STEMS = ["attn_q", "ffn_down", "tok_embd"]
TYPE_ORDER = ["Q8_0", "Q4_0", "Q5_0", "Q4_K"]
TYPE_FILES = ["q8_0", "q4_0", "q5_0", "q4_k"]
AUDIT_KEYS = ["tensors"]
TENSOR_KEYS = ["stem", "ne", "n_elem", "types"]
TYPE_KEYS = ["type", "nbytes", "nbytes_expected", "rmse", "requires_imatrix"]
RMSE_TOL = 5e-11  # 10 decimal digits; golden is ggml_quantize_chunk CPU


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def top_keys(text: str) -> list:
    return list(json.loads(text).keys())


def check_data_unmodified() -> None:
    if not DATA_DIR.is_dir():
        fail("missing /data/tensors")
    gold = sorted(p.name for p in FIX_DIR.iterdir() if p.is_file())
    got = sorted(p.name for p in DATA_DIR.iterdir() if p.is_file())
    if gold != got:
        fail(f"/data/tensors names {got} != fixture {gold}")
    for name in gold:
        if sha256(DATA_DIR / name) != sha256(FIX_DIR / name):
            fail(f"/data/tensors/{name} was modified")


def load_shape(path: Path) -> list[int]:
    ne = [int(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip() != ""]
    return ne


def n_elem_of(ne: list[int]) -> int:
    n = 1
    for x in ne:
        n *= x
    return n


def pad4(ne: list[int]) -> list[int]:
    out = list(ne) + [1] * (4 - len(ne))
    return out[:4]


def check_audit_text(text: str) -> dict:
    if not text.endswith("\n"):
        fail("quant_audit.json must end with a newline")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        fail(f"quant_audit.json is not valid JSON: {e}")
    if not isinstance(obj, dict):
        fail("quant_audit.json must be a JSON object")
    if top_keys(text) != AUDIT_KEYS:
        fail(f"quant_audit.json keys must be {AUDIT_KEYS} in that order, got {top_keys(text)}")
    tensors = obj["tensors"]
    if not isinstance(tensors, list) or len(tensors) != 3:
        fail("tensors must be an array of 3 entries")
    stems = [t.get("stem") for t in tensors]
    if stems != sorted(stems) or stems != STEMS:
        fail(f"tensors must be sorted by stem {STEMS}, got {stems}")
    gold = json.loads(GOLD_AUDIT.read_text(encoding="utf-8"))
    gold_by = {t["stem"]: t for t in gold["tensors"]}
    for t in tensors:
        if list(t.keys()) != TENSOR_KEYS:
            fail(f"tensor object keys must be {TENSOR_KEYS} in that order")
        if not isinstance(t["ne"], list) or len(t["ne"]) != 4:
            fail("ne must be an array of exactly 4 ints")
        if any(not isinstance(x, int) or isinstance(x, bool) for x in t["ne"]):
            fail("ne entries must be ints")
        if not isinstance(t["n_elem"], int) or isinstance(t["n_elem"], bool):
            fail("n_elem must be an int")
        stem = t["stem"]
        shape = load_shape(FIX_DIR / f"{stem}.shape")
        if t["ne"] != pad4(shape):
            fail(f"{stem}: ne {t['ne']} != padded fixture shape {pad4(shape)}")
        if t["n_elem"] != n_elem_of(shape):
            fail(f"{stem}: n_elem {t['n_elem']} != {n_elem_of(shape)}")
        types = t["types"]
        if not isinstance(types, list) or [x.get("type") for x in types] != TYPE_ORDER:
            fail(f"{stem}: types must be {TYPE_ORDER} in that order")
        gtypes = gold_by[stem]["types"]
        for i, (got, want, lname) in enumerate(zip(types, gtypes, TYPE_FILES)):
            if list(got.keys()) != TYPE_KEYS:
                fail(f"{stem} types[{i}] keys must be {TYPE_KEYS} in that order")
            packed = PACKED / f"{stem}.{lname}"
            if not packed.is_file():
                fail(f"missing packed file {packed}")
            if got["nbytes"] != packed.stat().st_size:
                fail(f"{stem}.{lname}: nbytes {got['nbytes']} != file size {packed.stat().st_size}")
            if got["nbytes_expected"] != got["nbytes"]:
                fail(f"{stem}.{lname}: nbytes_expected {got['nbytes_expected']} != nbytes {got['nbytes']}")
            if got["nbytes_expected"] != want["nbytes_expected"]:
                fail(
                    f"{stem}.{lname}: nbytes_expected {got['nbytes_expected']} "
                    f"!= ggml_row_size golden {want['nbytes_expected']}"
                )
            if got["requires_imatrix"] is not False:
                fail(f"{stem}.{lname}: requires_imatrix must be false")
            m = re.search(rf'"rmse"\s*:\s*(-?\d+\.\d+)', json.dumps(got) if False else "")
            # inspect original text for 10 decimal digits of this rmse
            if not isinstance(got["rmse"], (int, float)) or isinstance(got["rmse"], bool):
                fail("rmse must be a JSON number")
            if abs(float(got["rmse"]) - float(want["rmse"])) > RMSE_TOL:
                fail(f"{stem}.{lname}: rmse {got['rmse']} != golden {want['rmse']}")
        # textual 10-digit rmse in the original file for this stem
        for want in gtypes:
            pat = rf'"type"\s*:\s*"{want["type"]}"[^{{}}]*?"rmse"\s*:\s*(-?\d+\.\d+)'
            mm = re.search(pat, text)
            if not mm:
                fail(f"could not find rmse text for {stem} {want['type']}")
            frac = mm.group(1).split(".")[-1]
            if len(frac) != 10:
                fail(f"{stem} {want['type']} rmse must have exactly 10 digits after the decimal, got {mm.group(1)}")
    return obj


def run_cli(tensors_dir: Path, out_json: Path, packed_dir: Path) -> None:
    if not CLI.is_file() or not os.access(CLI, os.X_OK):
        fail("/results/bin/quant-audit must be an executable file")
    packed_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            str(CLI),
            "--tensors-dir", str(tensors_dir),
            "--out-json", str(out_json),
            "--packed-dir", str(packed_dir),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        fail(
            f"quant-audit exited {proc.returncode}\n"
            f"stdout: {proc.stdout[:500]!r}\nstderr: {proc.stderr[:800]!r}"
        )


def main() -> None:
    check_data_unmodified()
    if not PACKED.is_dir():
        fail("missing /results/packed")
    if not AUDIT.is_file():
        fail("missing /results/quant_audit.json")
    for stem in STEMS:
        for lname in TYPE_FILES:
            p = PACKED / f"{stem}.{lname}"
            g = GOLD_PACKED / f"{stem}.{lname}"
            if not p.is_file() or p.stat().st_size == 0:
                fail(f"missing or empty {p}")
            if p.read_bytes() != g.read_bytes():
                fail(f"{p} does not match ggml_quantize_chunk golden {g}")
    check_audit_text(AUDIT.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="quant-cli-") as td:
        td_path = Path(td)
        outj = td_path / "audit.json"
        pk = td_path / "packed"
        run_cli(DATA_DIR, outj, pk)
        for stem in STEMS:
            for lname in TYPE_FILES:
                a = pk / f"{stem}.{lname}"
                g = GOLD_PACKED / f"{stem}.{lname}"
                if a.read_bytes() != g.read_bytes():
                    fail(f"quant-audit re-run packed {stem}.{lname} drifted from golden")
        rerun = json.loads(outj.read_text(encoding="utf-8"))
        gold = json.loads(GOLD_AUDIT.read_text(encoding="utf-8"))
        # compare rmse / nbytes ignoring incidental key formatting
        if rerun != gold:
            # allow float string vs number if values match
            try:
                for a, b in zip(rerun["tensors"], gold["tensors"]):
                    if a["stem"] != b["stem"] or a["ne"] != b["ne"] or a["n_elem"] != b["n_elem"]:
                        fail(f"quant-audit re-run metadata mismatch {a} vs {b}")
                    for x, y in zip(a["types"], b["types"]):
                        if x["type"] != y["type"] or x["nbytes"] != y["nbytes"]:
                            fail(f"quant-audit re-run type mismatch {x} vs {y}")
                        if abs(float(x["rmse"]) - float(y["rmse"])) > RMSE_TOL:
                            fail(f"quant-audit re-run rmse {x['rmse']} != {y['rmse']}")
            except (KeyError, TypeError) as e:
                fail(f"quant-audit re-run JSON shape mismatch: {e}")

        # Perturb one tensor so a hardcoded dump of the original packed bytes fails.
        alt_dir = td_path / "alt"
        alt_dir.mkdir()
        for p in FIX_DIR.iterdir():
            shutil.copy2(p, alt_dir / p.name)
        blob = bytearray((alt_dir / "attn_q.f32").read_bytes())
        # flip the first float
        orig = struct.unpack_from("<f", blob, 0)[0]
        struct.pack_into("<f", blob, 0, orig + 3.5)
        (alt_dir / "attn_q.f32").write_bytes(bytes(blob))
        outj2 = td_path / "alt.json"
        pk2 = td_path / "alt-packed"
        run_cli(alt_dir, outj2, pk2)
        alt_q8 = (pk2 / "attn_q.q8_0").read_bytes()
        gold_q8 = (GOLD_PACKED / "attn_q.q8_0").read_bytes()
        if alt_q8 == gold_q8:
            fail("quant-audit ignored the perturbed tensor (packed Q8_0 identical)")
        alt_obj = json.loads(outj2.read_text(encoding="utf-8"))
        alt_rmse = None
        gold_rmse = None
        for t in alt_obj["tensors"]:
            if t["stem"] == "attn_q":
                alt_rmse = t["types"][0]["rmse"]
        for t in gold["tensors"]:
            if t["stem"] == "attn_q":
                gold_rmse = t["types"][0]["rmse"]
        if alt_rmse is None or abs(float(alt_rmse) - float(gold_rmse)) < 1e-12:
            fail("quant-audit RMSE did not change after perturbing attn_q")

    print("c5 checks passed", file=sys.stderr)


if __name__ == "__main__":
    main()
