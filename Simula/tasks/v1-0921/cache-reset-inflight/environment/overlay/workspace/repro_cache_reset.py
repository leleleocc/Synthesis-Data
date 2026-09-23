#!/usr/bin/env python3
"""Show prefix-cache reset while holders are live and leftover hashes after free."""
from __future__ import annotations

import sys

sys.path.insert(0, "/workspace/repo")

import torch
from vllm.sampling_params import SamplingParams
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_manager import KVCacheManager
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
)
from vllm.v1.request import Request

BLOCK = 4
TOKENS = [3, 3, 3, 3, 5, 5, 5, 5]


def make_req(rid, tokens):
    sp = SamplingParams(max_tokens=4)
    sp.update_from_generation_config({}, eos_token_id=100)
    return Request(
        request_id=rid,
        prompt_token_ids=list(tokens),
        sampling_params=sp,
        pooling_params=None,
        block_hasher=get_request_block_hasher(BLOCK, sha256),
    )


def main():
    init_none_hash(sha256)
    cfg = KVCacheConfig(
        num_blocks=8,
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
    req = make_req("live", TOKENS)
    computed, n_hit, _ = mgr.get_computed_blocks(req)
    mgr.allocate_slots(
        req,
        num_new_tokens=len(TOKENS) - n_hit,
        num_new_computed_tokens=n_hit,
        new_computed_blocks=computed,
        has_scheduled_reqs=False,
    )
    held = [b for b in mgr.block_pool.blocks if (not b.is_null) and b.ref_cnt > 0]
    print("holders", [(b.block_id, b.ref_cnt, b.block_hash is not None) for b in held])
    ok = mgr.reset_prefix_cache()
    print("reset while holders", ok, "map_empty", len(mgr.block_pool.cached_block_hash_to_block) == 0)

    mgr.free(req)
    ok2 = mgr.reset_prefix_cache()
    leftover = [b.block_id for b in mgr.block_pool.blocks if (not b.is_null) and b.block_hash is not None]
    print("reset after free", ok2, "leftover hashed blocks", leftover)

    twin = make_req("twin", TOKENS)
    computed2, n_hit2, _ = mgr.get_computed_blocks(twin)
    print("post-reset hit_tokens", n_hit2)


if __name__ == "__main__":
    main()
