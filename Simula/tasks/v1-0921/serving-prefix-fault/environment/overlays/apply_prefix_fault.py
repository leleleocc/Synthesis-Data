#!/usr/bin/env python3
"""Rewrite installed vLLM sources so prefix fingerprints and replica offsets diverge."""

from __future__ import annotations

from pathlib import Path

REPO = Path("/workspace/repo")

HASH_FILE = REPO / "vllm" / "v1" / "core" / "kv_cache_utils.py"
DETOK_FILE = REPO / "vllm" / "tokenizers" / "detokenizer_utils.py"

HASH_OLD = """    if not parent_block_hash:
        parent_block_hash = NONE_HASH

    curr_block_token_ids_tuple = tuple(curr_block_token_ids)
    return BlockHash(
        hash_function((parent_block_hash, curr_block_token_ids_tuple, extra_keys))
    )
"""

# Shared token-id window shift of 5 (the replica offset). Drop extra_keys and
# hash only curr_block_token_ids[5:] so prefix reuse no longer fingerprints
# the true prefix. Restoring extra_keys alone still leaves the window shift.
HASH_NEW = """    if not parent_block_hash:
        parent_block_hash = NONE_HASH

    curr_block_token_ids_tuple = tuple(curr_block_token_ids[5:])
    return BlockHash(
        hash_function((parent_block_hash, curr_block_token_ids_tuple))
    )
"""

DETOK_OLD = """# 5 is an arbitrary value that should work for all
# tokenizers (bigger = more conservative).
INITIAL_INCREMENTAL_DETOKENIZATION_OFFSET = 5
"""

DETOK_NEW = """# 5 is an arbitrary value that should work for all
# tokenizers (bigger = more conservative).
INITIAL_INCREMENTAL_DETOKENIZATION_OFFSET = 3
"""

CONVERT_OLD = """    # We do not need to convert the whole prompt to tokens.
    # Offset a little more in case we have special tokens.
    new_tokens = tokenizer.convert_ids_to_tokens(
        prompt_ids[-INITIAL_INCREMENTAL_DETOKENIZATION_OFFSET - 2 :],
        skip_special_tokens=skip_special_tokens,
    )
    read_offset = len(new_tokens)
    prefix_offset = max(read_offset - INITIAL_INCREMENTAL_DETOKENIZATION_OFFSET, 0)
"""

# Offset constant 3, drop the extra +2 tail, and swap prefix/read pairing
# against the same 5-token window the block hasher now skips. Restoring only
# the constant still leaves the pairing and hashed window disagreeing.
CONVERT_NEW = """    # We do not need to convert the whole prompt to tokens.
    # Offset a little more in case we have special tokens.
    new_tokens = tokenizer.convert_ids_to_tokens(
        prompt_ids[-INITIAL_INCREMENTAL_DETOKENIZATION_OFFSET :],
        skip_special_tokens=skip_special_tokens,
    )
    read_offset = max(len(new_tokens) - 5, 0)
    prefix_offset = len(new_tokens)
"""


def _replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected unique match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    if not HASH_FILE.is_file() or not DETOK_FILE.is_file():
        raise SystemExit("expected vLLM sources under /workspace/repo")
    _replace_once(HASH_FILE, HASH_OLD, HASH_NEW)
    _replace_once(DETOK_FILE, DETOK_OLD, DETOK_NEW)
    _replace_once(DETOK_FILE, CONVERT_OLD, CONVERT_NEW)
    hash_text = HASH_FILE.read_text(encoding="utf-8")
    detok_text = DETOK_FILE.read_text(encoding="utf-8")
    if "curr_block_token_ids_tuple, extra_keys" in hash_text:
        raise SystemExit("hash extra_keys still present")
    if "tuple(curr_block_token_ids[5:])" not in hash_text:
        raise SystemExit("hash window shift missing")
    if "INITIAL_INCREMENTAL_DETOKENIZATION_OFFSET = 5" in detok_text:
        raise SystemExit("detok offset constant unchanged")
    if "INITIAL_INCREMENTAL_DETOKENIZATION_OFFSET - 2" in detok_text:
        raise SystemExit("detok extra tail still present")
    if "prefix_offset = len(new_tokens)" not in detok_text:
        raise SystemExit("detok prefix/read pairing unchanged")


if __name__ == "__main__":
    main()
