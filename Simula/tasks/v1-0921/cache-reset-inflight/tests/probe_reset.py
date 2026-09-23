"""Live probes of reset_prefix_cache while holders exist and after free."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import torch

sys.path.insert(0, "/workspace/repo")

from vllm.sampling_params import SamplingParams
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_manager import KVCacheManager
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
from vllm.v1.kv_cache_interface import FullAttentionSpec, KVCacheConfig, KVCacheGroupSpec
from vllm.v1.request import Request

BLOCK = 4
TOKENS = [3, 3, 3, 3, 5, 5, 5, 5]
REPORT = Path("/workspace/cache_reset_report.json")


def make_req(rid: str, tokens=TOKENS) -> Request:
    sp = SamplingParams(max_tokens=4)
    sp.update_from_generation_config({}, eos_token_id=100)
    return Request(
        request_id=rid,
        prompt_token_ids=list(tokens),
        sampling_params=sp,
        pooling_params=None,
        block_hasher=get_request_block_hasher(BLOCK, sha256),
    )


def make_mgr() -> KVCacheManager:
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
    return KVCacheManager(
        cfg,
        max_model_len=32,
        scheduler_block_size=BLOCK,
        hash_block_size=BLOCK,
        enable_caching=True,
    )


def live_holders(mgr: KVCacheManager):
    return [b for b in mgr.block_pool.blocks if (not b.is_null) and b.ref_cnt > 0]


def run_live_sequence() -> dict:
    init_none_hash(sha256)
    mgr = make_mgr()
    req = make_req("live")
    computed, n_hit, _ = mgr.get_computed_blocks(req)
    allocated = mgr.allocate_slots(
        req,
        num_new_tokens=len(TOKENS) - n_hit,
        num_new_computed_tokens=n_hit,
        new_computed_blocks=computed,
        has_scheduled_reqs=False,
    )
    if allocated is None:
        raise RuntimeError("failed to allocate in-flight holder")
    held = live_holders(mgr)
    ids = [b.block_id for b in held]
    refs = [b.ref_cnt for b in held]
    map_before = len(mgr.block_pool.cached_block_hash_to_block)
    reset_while = mgr.reset_prefix_cache()
    map_after = len(mgr.block_pool.cached_block_hash_to_block)
    ids_after = [b.block_id for b in live_holders(mgr)]
    refs_after = [b.ref_cnt for b in live_holders(mgr)]

    mgr.free(req)
    leftover_before_reset = [
        b.block_id for b in mgr.block_pool.blocks if (not b.is_null) and b.block_hash is not None
    ]
    reset_after = mgr.reset_prefix_cache()
    map_empty = len(mgr.block_pool.cached_block_hash_to_block) == 0
    leftover = [
        b.block_id for b in mgr.block_pool.blocks if (not b.is_null) and b.block_hash is not None
    ]
    all_null = all(b.block_hash is None for b in mgr.block_pool.blocks)

    twin = make_req("twin")
    _computed2, n_hit2, _ = mgr.get_computed_blocks(twin)
    return {
        "while_holders": {
            "reset_returned": reset_while,
            "hash_map_still_populated": map_after > 0,
            "map_size_before": map_before,
            "map_size_after": map_after,
            "inflight_block_ids": ids,
            "inflight_refcnts": refs,
            "ids_unchanged": ids_after == ids,
            "refs_unchanged": refs_after == refs,
        },
        "after_free": {
            "reset_returned": reset_after,
            "hash_map_empty": map_empty,
            "all_block_hashes_null": all_null,
            "leftover_hashed_before_reset": leftover_before_reset,
            "leftover_hashed_after_reset": leftover,
        },
        "post_reset_shared_prefix": {
            "get_computed_blocks_hit_tokens": int(n_hit2),
            "allocate_reused_stale_pages": bool(n_hit2 > 0),
        },
    }


def load_report() -> dict:
    if not REPORT.is_file():
        raise FileNotFoundError(f"missing {REPORT}")
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    extra = set(data) - {"while_holders", "after_free", "post_reset_shared_prefix"}
    if extra:
        raise ValueError(f"unexpected keys {sorted(extra)}")
    return data


def main() -> int:
    live = run_live_sequence()
    report = load_report()
    failures: list[str] = []

    wh = report["while_holders"]
    if wh.get("reset_returned") is not False:
        failures.append("while_holders.reset_returned must be false")
    if wh.get("hash_map_still_populated") is not True:
        failures.append("while_holders.hash_map_still_populated must be true")
    if not wh.get("inflight_block_ids") or not wh.get("inflight_refcnts"):
        failures.append("while_holders must record inflight ids and refcnts")
    if live["while_holders"]["reset_returned"] is not False:
        failures.append(
            f"live reset while holders returned {live['while_holders']['reset_returned']}"
        )
    if not live["while_holders"]["hash_map_still_populated"]:
        failures.append("live hash map was emptied while holders still own pages")
    if not live["while_holders"]["ids_unchanged"] or not live["while_holders"]["refs_unchanged"]:
        failures.append("live in-flight block ids or refcnts changed during failed reset")

    af = report["after_free"]
    if af.get("reset_returned") is not True:
        failures.append("after_free.reset_returned must be true")
    if af.get("hash_map_empty") is not True:
        failures.append("after_free.hash_map_empty must be true")
    if af.get("all_block_hashes_null") is not True:
        failures.append("after_free.all_block_hashes_null must be true")
    if live["after_free"]["reset_returned"] is not True:
        failures.append("live reset after free did not return true")
    if not live["after_free"]["hash_map_empty"]:
        failures.append("live hash map still populated after true reset")
    if not live["after_free"]["all_block_hashes_null"]:
        failures.append(
            f"live leftover hashed blocks {live['after_free']['leftover_hashed_after_reset']}"
        )

    pr = report["post_reset_shared_prefix"]
    if pr.get("get_computed_blocks_hit_tokens") != 0:
        failures.append("report get_computed_blocks_hit_tokens must be 0")
    if pr.get("allocate_reused_stale_pages") is not False:
        failures.append("report allocate_reused_stale_pages must be false")
    if live["post_reset_shared_prefix"]["get_computed_blocks_hit_tokens"] != 0:
        failures.append(
            "live post-reset get_computed_blocks reused stale pages "
            f"(hit_tokens={live['post_reset_shared_prefix']['get_computed_blocks_hit_tokens']})"
        )

    if failures:
        print("state check: fail")
        for item in failures:
            print(f"reason: {item}")
        return 1
    print("normal case: pass")
    print("edge case: pass")
    print("error handling: pass")
    print("state check: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
