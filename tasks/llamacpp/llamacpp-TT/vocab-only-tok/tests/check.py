#!/usr/bin/env python3
"""Independent verifier for the vocab-only GGUF / tok-cli task."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/tests")
# Reuse a local GGUF reader (copied logic, no c2 import across candidates).
import struct
from typing import Any

GGUF_MAGIC = b"GGUF"
TYPE_NAMES = {
    0: "UINT8", 1: "INT8", 2: "UINT16", 3: "INT16", 4: "UINT32", 5: "INT32",
    6: "FLOAT32", 7: "BOOL", 8: "STRING", 9: "ARRAY", 10: "UINT64", 11: "INT64",
    12: "FLOAT64",
}

VOCAB_GOLDEN = Path("/tests/fixtures/spm_vocab.json")
PROMPTS_GOLDEN = Path("/tests/fixtures/prompts.txt")
DATA_VOCAB = Path("/data/spm_vocab.json")
DATA_PROMPTS = Path("/data/prompts.txt")
GGUF_PATH = Path("/results/tiny-vocab.gguf")
JSONL = Path("/results/tokens.jsonl")
CLI = Path("/results/bin/tok-cli")

JSONL_KEYS = ["line", "text", "n_tokens", "tokens", "detok"]
REQUIRED_KV = [
    "general.architecture",
    "tokenizer.ggml.model",
    "tokenizer.ggml.tokens",
    "tokenizer.ggml.scores",
    "tokenizer.ggml.token_type",
    "tokenizer.ggml.bos_token_id",
    "tokenizer.ggml.eos_token_id",
    "tokenizer.ggml.unknown_token_id",
    "tokenizer.ggml.add_bos_token",
    "tokenizer.ggml.add_eos_token",
    "tokenizer.ggml.add_space_prefix",
]


class GGUFError(Exception):
    pass


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unpack(fmt: str, data: bytes, off: int):
    size = struct.calcsize(fmt)
    if off + size > len(data):
        raise GGUFError(f"truncated GGUF at offset {off}")
    return struct.unpack_from(fmt, data, off)[0], off + size


def _read_str(data: bytes, off: int):
    n, off = _unpack("<Q", data, off)
    if off + n > len(data):
        raise GGUFError("truncated GGUF string")
    return data[off : off + n].decode("utf-8"), off + n


def _read_scalar(typ: int, data: bytes, off: int):
    if typ == 0:
        return _unpack("<B", data, off)
    if typ == 1:
        return _unpack("<b", data, off)
    if typ == 2:
        return _unpack("<H", data, off)
    if typ == 3:
        return _unpack("<h", data, off)
    if typ == 4:
        return _unpack("<I", data, off)
    if typ == 5:
        return _unpack("<i", data, off)
    if typ == 6:
        return _unpack("<f", data, off)
    if typ == 7:
        v, off = _unpack("<b", data, off)
        return bool(v), off
    if typ == 8:
        return _read_str(data, off)
    if typ == 10:
        return _unpack("<Q", data, off)
    if typ == 11:
        return _unpack("<q", data, off)
    if typ == 12:
        return _unpack("<d", data, off)
    raise GGUFError(f"unsupported gguf type {typ}")


def _read_value(typ: int, data: bytes, off: int):
    if typ == 9:
        atype, off = _unpack("<i", data, off)
        n, off = _unpack("<Q", data, off)
        items = []
        for _ in range(n):
            item, off = _read_value(atype, data, off)
            items.append(item)
        return ("ARRAY", atype, items), off
    return _read_scalar(typ, data, off)


def parse_gguf(raw: bytes):
    if raw[:4] != GGUF_MAGIC:
        raise GGUFError(f"bad magic {raw[:4]!r}")
    off = 4
    version, off = _unpack("<I", raw, off)
    n_tensors, off = _unpack("<q", raw, off)
    n_kv, off = _unpack("<q", raw, off)
    kv = []
    seen = set()
    alignment = 32
    for _ in range(n_kv):
        key, off = _read_str(raw, off)
        typ, off = _unpack("<i", raw, off)
        if typ not in TYPE_NAMES:
            raise GGUFError(f"unknown kv type {typ} for {key}")
        val, off = _read_value(typ, raw, off)
        if key in seen:
            raise GGUFError(f"duplicate key {key}")
        seen.add(key)
        kv.append((key, typ, val))
        if key == "general.alignment":
            if typ != 4:
                raise GGUFError("general.alignment must be UINT32")
            alignment = int(val)
    tensors = []
    for _ in range(n_tensors):
        name, off = _read_str(raw, off)
        n_dims, off = _unpack("<I", raw, off)
        if n_dims > 4:
            raise GGUFError("n_dims > 4")
        ne = [1, 1, 1, 1]
        for d in range(n_dims):
            v, off = _unpack("<q", raw, off)
            ne[d] = int(v)
        ggml_type, off = _unpack("<i", raw, off)
        toff, off = _unpack("<Q", raw, off)
        tensors.append((name, n_dims, ne, ggml_type, int(toff)))
    return version, kv, tensors, alignment


def check_data_unmodified() -> None:
    if not DATA_VOCAB.is_file() or not DATA_PROMPTS.is_file():
        fail("missing /data/spm_vocab.json or /data/prompts.txt")
    if sha256(DATA_VOCAB) != sha256(VOCAB_GOLDEN):
        fail("/data/spm_vocab.json was modified")
    if sha256(DATA_PROMPTS) != sha256(PROMPTS_GOLDEN):
        fail("/data/prompts.txt was modified")


def kv_map(kv):
    return {k: (t, v) for k, t, v in kv}


def arr_items(val):
    if not (isinstance(val, tuple) and val[0] == "ARRAY"):
        fail(f"expected ARRAY, got {val!r}")
    return val[1], val[2]


def check_gguf(raw: bytes, vocab: dict) -> None:
    if raw[:4] != b"GGUF":
        fail(f"tiny-vocab.gguf magic {raw[:4]!r} != b'GGUF'")
    try:
        version, kv, tensors, _align = parse_gguf(raw)
    except GGUFError as e:
        fail(f"tiny-vocab.gguf is not a well-formed GGUF v3 file: {e}")
    if version != 3:
        fail(f"GGUF version {version} != 3")
    if tensors:
        fail(f"vocab-only GGUF must include no weight tensors, got {len(tensors)}")
    keys = [k for k, _t, _v in kv]
    missing = [k for k in REQUIRED_KV if k not in keys]
    if missing:
        fail(f"tiny-vocab.gguf missing required KV keys {missing}")
    m = kv_map(kv)
    arch_t, arch_v = m["general.architecture"]
    if arch_t != 8 or arch_v != vocab["architecture"]:
        fail(f"general.architecture {arch_v!r} != {vocab['architecture']!r}")
    tm_t, tm_v = m["tokenizer.ggml.model"]
    if tm_t != 8 or tm_v != vocab["tokenizer_model"]:
        fail(f"tokenizer.ggml.model {tm_v!r} != {vocab['tokenizer_model']!r}")

    tok_type, tokens = arr_items(m["tokenizer.ggml.tokens"][1])
    if m["tokenizer.ggml.tokens"][0] != 9:
        fail("tokenizer.ggml.tokens must be ARRAY")
    if tok_type != 8:
        fail("tokenizer.ggml.tokens array must be STRING")
    if tokens != vocab["tokens"]:
        fail("tokenizer.ggml.tokens does not match /data/spm_vocab.json tokens")

    sc_type, scores = arr_items(m["tokenizer.ggml.scores"][1])
    if m["tokenizer.ggml.scores"][0] != 9 or sc_type != 6:
        fail("tokenizer.ggml.scores must be ARRAY of FLOAT32")
    if len(scores) != len(vocab["scores"]):
        fail("tokenizer.ggml.scores length mismatch")
    for a, b in zip(scores, vocab["scores"]):
        if abs(float(a) - float(b)) > 1e-6:
            fail("tokenizer.ggml.scores values mismatch")

    tt_type, ttypes = arr_items(m["tokenizer.ggml.token_type"][1])
    if m["tokenizer.ggml.token_type"][0] != 9 or tt_type not in (4, 5):
        fail("tokenizer.ggml.token_type must be ARRAY of UINT32 or INT32")
    if [int(x) for x in ttypes] != list(vocab["token_types"]):
        fail("tokenizer.ggml.token_type does not match vocab token_types")

    def u32(key, expected):
        t, v = m[key]
        if t not in (4, 5, 10, 11) or int(v) != int(expected):
            fail(f"{key} type={t} value={v!r} != {expected}")

    def flag(key, expected: bool):
        t, v = m[key]
        if t != 7 or bool(v) is not bool(expected):
            fail(f"{key} type={t} value={v!r} != {expected}")

    u32("tokenizer.ggml.bos_token_id", vocab["bos_id"])
    u32("tokenizer.ggml.eos_token_id", vocab["eos_id"])
    u32("tokenizer.ggml.unknown_token_id", vocab["unk_id"])
    flag("tokenizer.ggml.add_bos_token", vocab["add_bos"])
    flag("tokenizer.ggml.add_eos_token", vocab["add_eos"])
    flag("tokenizer.ggml.add_space_prefix", vocab["add_space_prefix"])


def parse_jsonl(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        fail("tokens.jsonl must end with a newline")
    rows = []
    for i, line in enumerate(text.splitlines(), 1):
        if line == "":
            fail("tokens.jsonl contains a blank line")
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            fail(f"tokens.jsonl line {i} is not JSON: {e}")
        if not isinstance(obj, dict):
            fail(f"tokens.jsonl line {i} must be an object")
        if list(obj.keys()) != JSONL_KEYS:
            fail(f"tokens.jsonl keys must be {JSONL_KEYS} in that order, got {list(obj.keys())}")
        rows.append(obj)
    return rows


def expected_prompt_rows() -> list[tuple[int, str]]:
    raw = PROMPTS_GOLDEN.read_text(encoding="utf-8")
    rows = []
    for i, line in enumerate(raw.splitlines(), 1):
        if line != "":
            rows.append((i, line))
    return rows


def check_jsonl_rows(rows: list[dict], vocab: dict) -> None:
    expected = expected_prompt_rows()
    if len(rows) != len(expected):
        fail(f"tokens.jsonl has {len(rows)} objects, expected {len(expected)} non-empty prompts")
    bos = int(vocab["bos_id"])
    eos = int(vocab["eos_id"])
    n_vocab = len(vocab["tokens"])
    for row, (lineno, text) in zip(rows, expected):
        if not isinstance(row["line"], int) or isinstance(row["line"], bool):
            fail("line must be an int")
        if row["line"] != lineno:
            fail(f"line {row['line']} != 1-based source index {lineno}")
        if row["text"] != text:
            fail(f"text {row['text']!r} != prompt {text!r}")
        toks = row["tokens"]
        if not isinstance(toks, list) or not toks:
            fail("tokens must be a non-empty array of ints")
        if any(not isinstance(t, int) or isinstance(t, bool) for t in toks):
            fail("tokens entries must be ints")
        if row["n_tokens"] != len(toks):
            fail(f"n_tokens {row['n_tokens']} != len(tokens) {len(toks)}")
        if any(t < 0 or t >= n_vocab for t in toks):
            fail(f"token id out of range in {toks}")
        if vocab["add_bos"] and toks[0] != bos:
            fail(f"add_special+add_bos: first token {toks[0]} != bos_id {bos}")
        if vocab["add_eos"] is False and toks[-1] == eos and text.find("</s>") < 0:
            # add_eos false: do not require absence of eos if the text tokenized to it,
            # but the last token should not be auto-appended eos for these prompts
            pass
        if not isinstance(row["detok"], str):
            fail("detok must be a string")
        if row["detok"] == "":
            fail("detok is empty")


def run_cli(model: Path, prompts: Path, out: Path) -> None:
    if not CLI.is_file() or not os.access(CLI, os.X_OK):
        fail("/results/bin/tok-cli must be an executable file")
    proc = subprocess.run(
        [str(CLI), "--model", str(model), "--prompts", str(prompts), "--out", str(out)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        fail(
            f"tok-cli exited {proc.returncode}\n"
            f"stdout: {proc.stdout[:500]!r}\nstderr: {proc.stderr[:800]!r}"
        )


def main() -> None:
    check_data_unmodified()
    vocab = json.loads(VOCAB_GOLDEN.read_text(encoding="utf-8"))
    if not GGUF_PATH.is_file() or GGUF_PATH.stat().st_size == 0:
        fail("missing or empty /results/tiny-vocab.gguf")
    if not JSONL.is_file():
        fail("missing /results/tokens.jsonl")
    check_gguf(GGUF_PATH.read_bytes(), vocab)
    rows = parse_jsonl(JSONL)
    check_jsonl_rows(rows, vocab)

    with tempfile.TemporaryDirectory(prefix="tok-cli-") as td:
        td_path = Path(td)
        out2 = td_path / "tokens.jsonl"
        run_cli(GGUF_PATH, DATA_PROMPTS, out2)
        rows2 = parse_jsonl(out2)
        if rows2 != rows:
            fail("tok-cli re-run on the original model/prompts drifted from tokens.jsonl")

        # Alternate prompts: CLI must honor --prompts, not a hardcoded dump.
        alt_prompts = td_path / "alt.txt"
        alt_prompts.write_text("hello\nworld\n", encoding="utf-8")
        out3 = td_path / "alt.jsonl"
        run_cli(GGUF_PATH, alt_prompts, out3)
        rows3 = parse_jsonl(out3)
        if len(rows3) != 2:
            fail(f"tok-cli --prompts alt produced {len(rows3)} rows, expected 2")
        if rows3[0]["text"] != "hello" or rows3[1]["text"] != "world":
            fail("tok-cli ignored --prompts contents")
        if rows3[0]["tokens"] == rows[0]["tokens"] and rows3[0]["text"] != rows[0]["text"]:
            fail("tok-cli appears to ignore prompt text")
        if rows3 == rows:
            fail("tok-cli ignored --prompts (output identical to original)")

    print("c6 checks passed", file=sys.stderr)


if __name__ == "__main__":
    main()
