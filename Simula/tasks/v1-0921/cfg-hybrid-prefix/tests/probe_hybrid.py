"""Live hybrid prefix-cache config discriminator."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import torch

sys.path.insert(0, "/workspace/repo")

from vllm.config.cache import CacheConfig, _layout_from_name
from vllm.v1.attention.backends.utils import resolve_kv_cache_layout
from vllm.v1.core.kv_cache_coordinator import get_kv_cache_coordinator
from vllm.v1.core.kv_cache_utils import resolve_kv_cache_block_sizes
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
    MambaSpec,
)
from vllm.v1.kv_cache_layout import KVCacheLayout

REPORT = Path("/workspace/hybrid_cache_config.json")


class _Par:
    decode_context_parallel_size = 1


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


def mixed_hnc_specs():
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
    return [attn, mamba]


def load_report() -> dict:
    if not REPORT.is_file():
        raise FileNotFoundError(f"missing {REPORT}")
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    extra = set(data) - {"illegal_unit", "illegal_layout", "aliases", "legal"}
    if extra:
        raise ValueError(f"unexpected keys {sorted(extra)}")
    return data


def try_unit(unit: int):
    cache = CacheConfig()
    cache.block_size = 16
    cache.enable_prefix_caching = True
    cache.prefix_match_unit = unit
    cfg = KVCacheConfig(num_blocks=8, kv_cache_tensors=[], kv_cache_groups=groups())
    return resolve_kv_cache_block_sizes(cfg, _V(cache))


def try_layout(name: str):
    """Request a non-compact layout with only non-compact candidates.

    Mixed HNC then empties the candidate set and raises the block-compact error
    from resolve_kv_cache_layout (not the later VLLM_KV_CACHE_LAYOUT mismatch).
    """
    cache = CacheConfig()
    cache.block_size = 16
    cache.enable_prefix_caching = True
    cache.prefix_match_unit = 16
    v = _V(cache)
    cache.kv_cache_layout = None
    prev = os.environ.get("VLLM_KV_CACHE_LAYOUT")
    os.environ["VLLM_KV_CACHE_LAYOUT"] = name
    try:
        return resolve_kv_cache_layout(
            v,
            supported_layouts=[["LHBNC"]],
            kv_cache_specs=mixed_hnc_specs(),
        )
    finally:
        if prev is None:
            os.environ.pop("VLLM_KV_CACHE_LAYOUT", None)
        else:
            os.environ["VLLM_KV_CACHE_LAYOUT"] = prev


def construct_legal():
    cache = CacheConfig()
    cache.block_size = 16
    cache.enable_prefix_caching = True
    cache.prefix_match_unit = 16
    cache.kv_cache_layout = "LBNHC"
    cfg = KVCacheConfig(
        num_blocks=8,
        kv_cache_tensors=[],
        kv_cache_groups=groups(),
        kv_cache_layout="LBNHC",
    )
    sched, hashed = resolve_kv_cache_block_sizes(cfg, _V(cache))
    coord = get_kv_cache_coordinator(
        kv_cache_config=cfg,
        max_model_len=64,
        max_in_flight_tokens=64,
        use_eagle=False,
        enable_caching=True,
        enable_kv_cache_events=False,
        dcp_world_size=1,
        pcp_world_size=1,
        scheduler_block_size=sched,
        hash_block_size=hashed,
    )
    return sched, hashed, type(coord).__name__


def main() -> int:
    failures: list[str] = []
    report = load_report()

    iu = report["illegal_unit"]
    if iu.get("prefix_match_unit") != 24 or iu.get("group_block_sizes") != [16, 32]:
        failures.append("illegal_unit must record unit 24 and groups [16, 32]")
    if iu.get("raised") is not True or "prefix_match_unit" not in str(iu.get("error_contains", "")):
        failures.append("illegal_unit must raise with prefix_match_unit in the message")
    try:
        result = try_unit(24)
        failures.append(f"live unit=24 did not raise, got {result}")
        print("error handling: fail")
    except Exception as exc:
        if "prefix_match_unit" not in str(exc):
            failures.append(f"live unit=24 error {exc!r} missing prefix_match_unit")
        else:
            print("error handling: pass")

    il = report["illegal_layout"]
    if il.get("requested_layout") != "LHBNC" or il.get("mixed_hnc") is not True:
        failures.append("illegal_layout must record LHBNC with mixed_hnc true")
    if il.get("raised") is not True or "block-compact" not in str(il.get("error_contains", "")):
        failures.append("illegal_layout must raise with block-compact in the message")
    try:
        layout = try_layout("LHBNC")
        failures.append(f"live mixed-HNC LHBNC did not raise, got {layout}")
        print("edge case: fail")
    except Exception as exc:
        if "block-compact" not in str(exc):
            failures.append(f"live LHBNC error {exc!r} missing block-compact")
        else:
            print("edge case: pass")

    aliases = report["aliases"]
    if aliases.get("NHD") != "LBNHC" or aliases.get("HND") != "LBHNC":
        failures.append("aliases must map NHD->LBNHC and HND->LBHNC")
    try:
        nhd = _layout_from_name("NHD")
        hnd = _layout_from_name("HND")
        if getattr(nhd, "name", str(nhd)) != "LBNHC":
            failures.append(f"live NHD resolved to {nhd}, expected LBNHC")
        if getattr(hnd, "name", str(hnd)) != "LBHNC":
            failures.append(f"live HND resolved to {hnd}, expected LBHNC")
    except Exception as exc:
        failures.append(f"live alias resolve failed: {exc}")

    legal = report["legal"]
    expected_legal = {
        "prefix_match_unit": 16,
        "group_block_sizes": [16, 32],
        "scheduler_block_size": 32,
        "hash_block_size": 16,
        "layout": "LBNHC",
        "coordinator_constructs": True,
    }
    for key, value in expected_legal.items():
        if legal.get(key) != value:
            failures.append(f"legal.{key}={legal.get(key)!r} expected {value!r}")
    try:
        sched, hashed, name = construct_legal()
        if sched != 32 or hashed != 16:
            failures.append(f"live legal sizes {(sched, hashed)} != (32, 16)")
        if "Hybrid" not in name:
            failures.append(f"live coordinator was {name}, expected HybridKVCacheCoordinator")
        else:
            print("normal case: pass")
    except Exception as exc:
        failures.append(f"legal HybridKVCacheCoordinator failed to construct: {exc}")
        print("normal case: fail")

    print("state check: pass" if not failures else "state check: fail")

    if failures:
        for item in failures:
            print(f"reason: {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
