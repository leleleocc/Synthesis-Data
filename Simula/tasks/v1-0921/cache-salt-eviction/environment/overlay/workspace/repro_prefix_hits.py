#!/usr/bin/env python3
"""Print live prefix-cache isolation and allocation-pressure symptoms."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/workspace/repo")

import torch
from vllm.lora.request import LoRARequest
from vllm.sampling_params import SamplingParams
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_manager import KVCacheManager
from vllm.v1.core.kv_cache_utils import (
    generate_block_hash_extra_keys,
    get_request_block_hasher,
    hash_block_tokens,
    init_none_hash,
)
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
)
from vllm.v1.request import Request

BLOCK = 4
TOKENS = [7, 7, 7, 7, 9, 9, 9, 9, 1, 2, 3, 4]


def make_req(rid, tokens, salt=None, lora=None):
    sp = SamplingParams(max_tokens=8)
    sp.update_from_generation_config({}, eos_token_id=100)
    return Request(
        request_id=rid,
        prompt_token_ids=list(tokens),
        sampling_params=sp,
        pooling_params=None,
        lora_request=lora,
        cache_salt=salt,
        block_hasher=get_request_block_hasher(BLOCK, sha256),
    )


def first_hash(req):
    extra, _ = generate_block_hash_extra_keys(req, 0, BLOCK, 0)
    return hash_block_tokens(sha256, None, req.all_token_ids[:BLOCK], extra).hex()


def main():
    init_none_hash(sha256)
    a = make_req("a", TOKENS[:8], salt="alpha")
    b = make_req("b", TOKENS[:8], salt="bravo")
    ha, hb = first_hash(a), first_hash(b)
    print("salt isolation:", "same" if ha == hb else "different", ha, hb)

    lx = LoRARequest(lora_name="sql-adapter", lora_int_id=1, lora_path="/tmp/x")
    ly = LoRARequest(lora_name="chat-adapter", lora_int_id=2, lora_path="/tmp/y")
    x = make_req("x", TOKENS[:8], lora=lx)
    y = make_req("y", TOKENS[:8], lora=ly)
    hx, hy = first_hash(x), first_hash(y)
    print("lora isolation:", "same" if hx == hy else "different", hx, hy)

    cfg = KVCacheConfig(
        num_blocks=6,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec(
                ["layer"],
                FullAttentionSpec(
                    block_size=BLOCK,
                    num_kv_heads=1,
                    head_size=8,
                    dtype=torch.float32,
                ),
            )
        ],
    )
    mgr = KVCacheManager(
        cfg,
        max_model_len=32,
        scheduler_block_size=BLOCK,
        hash_block_size=BLOCK,
        enable_caching=True,
    )
    warm = make_req("warm", TOKENS[:8])
    computed, n_hit, _ = mgr.get_computed_blocks(warm)
    allocated = mgr.allocate_slots(
        warm, num_new_tokens=len(TOKENS[:8]) - n_hit,
        num_new_computed_tokens=n_hit, new_computed_blocks=computed,
        has_scheduled_reqs=False,
    )
    print("warm allocate", None if allocated is None else "ok", "hits", n_hit)

    probe = make_req("probe", TOKENS)  # prefix + unique tail
    computed, n_hit, _ = mgr.get_computed_blocks(probe)
    prefix_blocks = list(computed.blocks[0]) if computed.blocks else []
    ids_before = [blk.block_id for blk in prefix_blocks]
    refs_before = [blk.ref_cnt for blk in prefix_blocks]
    result = mgr.allocate_slots(
        probe,
        num_new_tokens=len(TOKENS) - n_hit,
        num_new_computed_tokens=n_hit,
        new_computed_blocks=computed,
        has_scheduled_reqs=False,
    )
    ids_after = [blk.block_id for blk in prefix_blocks]
    refs_after = [blk.ref_cnt for blk in prefix_blocks]
    print("allocate_slots", result)
    print("prefix ids before", ids_before, "after", ids_after)
    print("prefix refs before", refs_before, "after", refs_after)


if __name__ == "__main__":
    main()
