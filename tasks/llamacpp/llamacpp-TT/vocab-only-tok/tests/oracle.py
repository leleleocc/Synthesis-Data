#!/usr/bin/env python3
"""Vocab-only GGUF + tokens.jsonl oracle for c6."""
from __future__ import annotations

import json
import os
import struct
import sys
from collections import OrderedDict
from pathlib import Path

GGUF_MAGIC = b"GGUF"
UINT8, INT8, UINT16, INT16, UINT32, INT32, FLOAT32, BOOL, STRING, ARRAY, UINT64, INT64, FLOAT64 = range(13)

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

REQUIRED_KEYS = {
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
}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.off = 0

    def take(self, n: int) -> bytes:
        if self.off + n > len(self.data):
            fail(f"truncated GGUF at {self.off}, need {n}")
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


def read_value(r: Reader, typ: int):
    if typ == STRING:
        return r.string()
    if typ == BOOL:
        return bool(r.take(1)[0])
    if typ == UINT32:
        return struct.unpack("<I", r.take(4))[0]
    if typ == INT32:
        return struct.unpack("<i", r.take(4))[0]
    if typ == FLOAT32:
        return struct.unpack("<f", r.take(4))[0]
    if typ == UINT64:
        return struct.unpack("<Q", r.take(8))[0]
    if typ == INT64:
        return struct.unpack("<q", r.take(8))[0]
    if typ == UINT8:
        return r.take(1)[0]
    if typ == INT8:
        return struct.unpack("<b", r.take(1))[0]
    if typ == ARRAY:
        et = r.i32()
        n = r.u64()
        if et == STRING:
            return [r.string() for _ in range(n)]
        if et == FLOAT32:
            return list(struct.unpack("<" + "f" * n, r.take(4 * n)))
        if et == INT32:
            return list(struct.unpack("<" + "i" * n, r.take(4 * n)))
        if et == UINT32:
            return list(struct.unpack("<" + "I" * n, r.take(4 * n)))
        if et == INT8:
            return list(struct.unpack("<" + "b" * n, r.take(n)))
        if et not in SCALAR_SIZE:
            fail(f"unsupported array et {et}")
        r.take(SCALAR_SIZE[et] * n)
        return f"<array {et} x {n}>"
    if typ in SCALAR_SIZE:
        r.take(SCALAR_SIZE[typ])
        return None
    fail(f"unsupported kv type {typ}")


def parse_gguf(path: Path):
    data = path.read_bytes()
    r = Reader(data)
    if r.take(4) != GGUF_MAGIC:
        fail(f"{path} magic is not GGUF")
    version = r.u32()
    n_tensors = r.i64()
    n_kv = r.i64()
    kv = OrderedDict()
    for _ in range(n_kv):
        key = r.string()
        typ = r.i32()
        kv[key] = (typ, read_value(r, typ))
    tensors = []
    for _ in range(n_tensors):
        name = r.string()
        n_dims = r.u32()
        ne = [r.i64() for _ in range(4)]
        ggml_type = r.i32()
        offset = r.u64()
        tensors.append(name)
    return {"version": version, "n_tensors": n_tensors, "n_kv": n_kv, "kv": kv, "tensors": tensors}


def main() -> None:
    vocab_path = Path("/data/spm_vocab.json")
    gguf_path = Path("/results/tiny-vocab.gguf")
    jsonl_path = Path("/results/tokens.jsonl")
    prompts_path = Path("/data/prompts.txt")
    if not vocab_path.is_file():
        fail("missing /data/spm_vocab.json")
    if not gguf_path.is_file():
        fail("missing /results/tiny-vocab.gguf")
    if not jsonl_path.is_file():
        fail("missing /results/tokens.jsonl")
    if not prompts_path.is_file():
        fail("missing /data/prompts.txt")

    vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
    parsed = parse_gguf(gguf_path)
    if parsed["version"] != 3:
        fail(f"GGUF version {parsed['version']} != 3")
    if parsed["n_tensors"] != 0:
        fail("vocab-only GGUF must include no weight tensors")
    keys = set(parsed["kv"].keys())
    missing = REQUIRED_KEYS - keys
    if missing:
        fail(f"GGUF missing keys {sorted(missing)}")

    def val(key):
        return parsed["kv"][key][1]

    if val("general.architecture") != vocab["architecture"]:
        fail("general.architecture mismatch")
    if val("tokenizer.ggml.model") != vocab["tokenizer_model"]:
        fail("tokenizer.ggml.model mismatch")
    tokens = val("tokenizer.ggml.tokens")
    if not isinstance(tokens, list) or tokens != vocab["tokens"]:
        fail("tokenizer.ggml.tokens does not match the vocab JSON")
    scores = val("tokenizer.ggml.scores")
    if not isinstance(scores, list) or len(scores) != len(tokens):
        fail("tokenizer.ggml.scores length mismatch")
    for a, b in zip(scores, vocab["scores"]):
        if abs(float(a) - float(b)) > 1e-5:
            fail("tokenizer.ggml.scores values mismatch")
    ttypes = val("tokenizer.ggml.token_type")
    if list(ttypes) != list(vocab["token_types"]):
        fail("tokenizer.ggml.token_type mismatch")
    if int(val("tokenizer.ggml.bos_token_id")) != int(vocab["bos_id"]):
        fail("bos_token_id mismatch")
    if int(val("tokenizer.ggml.eos_token_id")) != int(vocab["eos_id"]):
        fail("eos_token_id mismatch")
    if int(val("tokenizer.ggml.unknown_token_id")) != int(vocab["unk_id"]):
        fail("unknown_token_id mismatch")
    if bool(val("tokenizer.ggml.add_bos_token")) != bool(vocab["add_bos"]):
        fail("add_bos_token mismatch")
    if bool(val("tokenizer.ggml.add_eos_token")) != bool(vocab["add_eos"]):
        fail("add_eos_token mismatch")
    if bool(val("tokenizer.ggml.add_space_prefix")) != bool(vocab["add_space_prefix"]):
        fail("add_space_prefix mismatch")

    raw_b = jsonl_path.read_bytes()
    if not raw_b.endswith(b"\n"):
        fail("tokens.jsonl must end with a newline")
    lines = raw_b.decode("utf-8").splitlines()
    if lines and lines[-1] == "":
        lines = lines[:-1]
    prompt_lines = prompts_path.read_text(encoding="utf-8").splitlines()
    # Instruction: tokenize each non-empty line; line is 1-based index including blanks that were skipped.
    expected_rows = []
    for i, text in enumerate(prompt_lines, start=1):
        if text != "":
            expected_rows.append((i, text))
    if len(lines) != len(expected_rows):
        fail(f"tokens.jsonl has {len(lines)} objects, expected {len(expected_rows)} non-empty prompts")

    decoder = json.JSONDecoder(object_pairs_hook=OrderedDict)
    token_to_id = {t: i for i, t in enumerate(vocab["tokens"])}
    bos_id = int(vocab["bos_id"])
    add_bos = bool(vocab["add_bos"])
    # Space prefix marker used by SPM.
    sp_space = chr(0x2581)

    for raw_line, (lineno, text) in zip(lines, expected_rows):
        obj, idx = decoder.raw_decode(raw_line)
        if raw_line[idx:].strip() != "":
            fail(f"tokens.jsonl line has trailing junk: {raw_line!r}")
        if list(obj.keys()) != ["line", "text", "n_tokens", "tokens", "detok"]:
            fail(f"tokens.jsonl keys {list(obj.keys())}")
        if not isinstance(obj["line"], int) or isinstance(obj["line"], bool):
            fail("line must be a JSON integer")
        if obj["line"] != lineno:
            fail(f"line {obj['line']} != {lineno}")
        if obj["text"] != text:
            fail(f"text {obj['text']!r} != {text!r}")
        if not isinstance(obj["n_tokens"], int) or isinstance(obj["n_tokens"], bool):
            fail("n_tokens must be a JSON integer")
        if not isinstance(obj["tokens"], list) or not all(isinstance(t, int) and not isinstance(t, bool) for t in obj["tokens"]):
            fail("tokens must be an array of ints")
        if obj["n_tokens"] != len(obj["tokens"]):
            fail("n_tokens != len(tokens)")
        if obj["n_tokens"] < 1:
            fail("n_tokens must be >= 1")
        if add_bos and obj["tokens"][0] != bos_id:
            fail("add_special=true should prefix BOS")
        if not isinstance(obj["detok"], str):
            fail("detok must be a string")
        # detok with remove_special=false should still be non-empty and related to the prompt.
        if obj["detok"] == "":
            fail("detok is empty")
        # All token ids in vocab range.
        n_vocab = len(vocab["tokens"])
        for tid in obj["tokens"]:
            if tid < 0 or tid >= n_vocab:
                fail(f"token id {tid} out of vocab range")
    print("oracle: vocab GGUF and tokens.jsonl match")


if __name__ == "__main__":
    main()
