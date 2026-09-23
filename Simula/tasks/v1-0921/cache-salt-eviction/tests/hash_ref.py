"""Independent sha256 prefix-cache hashes (pickle protocol, vLLM extra-key order)."""
from __future__ import annotations

import hashlib
import pickle
from typing import Any, Sequence


NONE_HASH_SEED = "vllm-none-hash"


def sha256_pickle(obj: Any) -> bytes:
    return hashlib.sha256(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)).digest()


def none_hash() -> bytes:
    return sha256_pickle(NONE_HASH_SEED)


def extra_keys(
    cache_salt: str | None,
    lora_name: str | None,
    start_token_idx: int,
) -> tuple[Any, ...] | None:
    keys: list[Any] = []
    if lora_name:
        keys.append(lora_name)
    if start_token_idx == 0 and cache_salt:
        keys.append(cache_salt)
    return tuple(keys) if keys else None


def first_block_hash_hex(
    tokens: Sequence[int],
    cache_salt: str | None,
    lora_name: str | None,
    block_size: int = 4,
) -> str:
    extra = extra_keys(cache_salt, lora_name, 0)
    digest = sha256_pickle((none_hash(), tuple(tokens[:block_size]), extra))
    return digest.hex()
