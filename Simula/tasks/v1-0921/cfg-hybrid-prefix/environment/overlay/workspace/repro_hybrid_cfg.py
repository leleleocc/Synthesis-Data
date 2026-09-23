#!/usr/bin/env python3
import sys

sys.path.insert(0, "/workspace/repo")

import torch
from vllm.config.cache import CacheConfig, _layout_from_name
from vllm.v1.core.kv_cache_utils import resolve_kv_cache_block_sizes
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
    MambaSpec,
)
from vllm.v1.kv_cache_layout import KVCacheLayout


class _Par:
    decode_context_parallel_size = 1


class _Xfer:
    pass


class _V:
    def __init__(self, cache):
        self.cache_config = cache
        self.parallel_config = _Par()
        self.kv_transfer_config = None


def groups():
    attn = FullAttentionSpec(
        block_size=16, num_kv_heads=2, head_size=64, dtype=torch.float16
    )
    mamba = MambaSpec(
        block_size=32,
        shapes=((8, 16),),
        dtypes=(torch.float32,),
        mamba_cache_mode="align",
        num_heads=1,
    )
    return [
        KVCacheGroupSpec(["attn"], attn),
        KVCacheGroupSpec(["mamba"], mamba),
    ]


def main():
    cache = CacheConfig()
    cache.block_size = 16
    cache.enable_prefix_caching = True
    cache.prefix_match_unit = 24
    cfg = KVCacheConfig(num_blocks=8, kv_cache_tensors=[], kv_cache_groups=groups())
    try:
        print("unit24", resolve_kv_cache_block_sizes(cfg, _V(cache)))
    except Exception as exc:
        print("unit24 raised", exc)

    print("LHBNC compact", KVCacheLayout.LHBNC.is_block_compact)
    try:
        print("alias NHD", _layout_from_name("NHD"))
    except Exception as exc:
        print("alias NHD failed", exc)
    try:
        print("alias HND", _layout_from_name("HND"))
    except Exception as exc:
        print("alias HND failed", exc)


if __name__ == "__main__":
    main()
