#!/bin/bash
# Vocab description and prompts for a vocab-only GGUF / tokenize job.
set -euo pipefail

mkdir -p /data
python3 - <<'PY'
import json
from pathlib import Path

# SPM-style pieces plus the 256 byte fallback tokens llama.cpp expects for SPM.
# chr(0x2581) is the SentencePiece space marker.
tokens = ["<unk>", "<s>", "</s>", chr(0x2581), "hello", "world", "ing", "the", "cat", "sat"]
# byte tokens <0x00> .. <0xFF>
for i in range(256):
    tokens.append(f"<0x{i:02X}>")

n = len(tokens)
# Scores: control/unk low, pieces higher, bytes 0.
scores = []
token_types = []
for i, t in enumerate(tokens):
    if t == "<unk>":
        scores.append(0.0)
        token_types.append(2)  # UNKNOWN
    elif t in ("<s>", "</s>"):
        scores.append(0.0)
        token_types.append(3)  # CONTROL
    elif t.startswith("<0x"):
        scores.append(0.0)
        token_types.append(6)  # BYTE
    else:
        scores.append(float(-i) * 0.1)
        token_types.append(1)  # NORMAL

doc = {
    "architecture": "llama",
    "tokenizer_model": "llama",
    "tokens": tokens,
    "scores": scores,
    "token_types": token_types,
    "bos_id": 1,
    "eos_id": 2,
    "unk_id": 0,
    "add_bos": True,
    "add_eos": False,
    "add_space_prefix": True,
}
Path("/data/spm_vocab.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

prompts = """hello world
the cat sat
Hello
ing the
"""
Path("/data/prompts.txt").write_text(prompts, encoding="utf-8")
print("vocab tokens", n)
PY

chmod a+r /data/spm_vocab.json /data/prompts.txt
exit 0
