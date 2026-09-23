"""Discriminator for salt/LoRA hash isolation plus allocate_slots pressure."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, "/workspace/repo")
# Prefer the verifier oracle over any agent-written /workspace/repo/hash_ref.py.
sys.path.insert(0, "/tests")

from hash_ref import extra_keys as ref_extra_keys
from hash_ref import first_block_hash_hex
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
from vllm.v1.kv_cache_interface import FullAttentionSpec, KVCacheConfig, KVCacheGroupSpec
from vllm.v1.request import Request

REPORT = Path("/workspace/prefix_hit_table.json")
BLOCK = 4
TOKENS = [7, 7, 7, 7, 9, 9, 9, 9]
ROWS = [
    {"tokens": TOKENS, "cache_salt": "alpha", "lora_name": None},
    {"tokens": TOKENS, "cache_salt": "bravo", "lora_name": None},
    {"tokens": TOKENS, "cache_salt": None, "lora_name": "sql-adapter"},
    {"tokens": TOKENS, "cache_salt": None, "lora_name": "chat-adapter"},
    {"tokens": TOKENS, "cache_salt": "alpha", "lora_name": "sql-adapter"},
]


def _load() -> dict:
    assert REPORT.is_file(), f"missing report {REPORT}"
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "report must be a JSON object"
    extra = set(data) - {"hash_isolation", "cross_hits", "allocation_pressure"}
    assert not extra, f"unexpected top-level keys: {sorted(extra)}"
    return data


def _make_req(rid: str, tokens, salt=None, lora=None) -> Request:
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


def _lora(name: str, i: int) -> LoRARequest:
    return LoRARequest(lora_name=name, lora_int_id=i, lora_path=f"/tmp/{name}")


@pytest.fixture(scope="module")
def report():
    init_none_hash(sha256)
    return _load()


def test_hash_isolation_against_independent_reference(report):
    rows = report["hash_isolation"]
    assert isinstance(rows, list) and len(rows) == 5, "hash_isolation must have 5 rows"
    for i, spec in enumerate(ROWS):
        row = rows[i]
        assert row["tokens"] == spec["tokens"], f"row {i} tokens copied/altered"
        assert row["cache_salt"] == spec["cache_salt"], f"row {i} cache_salt mismatch"
        assert row["lora_name"] == spec["lora_name"], f"row {i} lora_name mismatch"
        assert row["n_full_blocks"] == 2, f"row {i} n_full_blocks"
        expected = first_block_hash_hex(
            spec["tokens"], spec["cache_salt"], spec["lora_name"], BLOCK
        )
        got = row["first_block_hash_hex"]
        assert isinstance(got, str) and len(got) == 64, f"row {i} hash is not sha256 hex"
        assert got == expected, (
            f"row {i} first_block_hash_hex {got} != independent sha256 {expected}"
        )
    print("normal case: pass")


def test_cross_hits_are_false_and_same_identity_matches(report):
    rows = report["hash_isolation"]
    hashes = [row["first_block_hash_hex"] for row in rows]
    assert hashes[0] != hashes[1], "salt isolation failed: alpha == bravo"
    assert hashes[2] != hashes[3], "lora isolation failed: sql-adapter == chat-adapter"
    assert hashes[0] != hashes[4], "combined salt+lora shares salt-only alpha hash"
    # Same tokens, salt, LoRA must match if computed twice.
    again = first_block_hash_hex(TOKENS, "alpha", "sql-adapter", BLOCK)
    assert hashes[4] == again, "identical salt+lora request hashes diverged"
    for spec, pair in zip(
        report["cross_hits"],
        [(0, 1), (2, 3), (0, 4)],
        strict=True,
    ):
        assert spec["a"] == pair[0] and spec["b"] == pair[1]
        assert spec["same_first_block_hash"] is False
        assert hashes[pair[0]] != hashes[pair[1]]
    print("edge case: pass")


def test_live_extra_keys_fold_salt_and_lora_only_on_first_block():
    init_none_hash(sha256)
    salt_req = _make_req("s", TOKENS, salt="alpha")
    extra0, _ = generate_block_hash_extra_keys(salt_req, 0, BLOCK, 0)
    extra1, _ = generate_block_hash_extra_keys(salt_req, BLOCK, 2 * BLOCK, 0)
    assert extra0 == ref_extra_keys("alpha", None, 0), (
        f"live first-block extra_keys {extra0} missing cache_salt"
    )
    assert extra1 == ref_extra_keys("alpha", None, BLOCK), (
        f"salt re-attached on later block extra_keys={extra1}"
    )
    lora_req = _make_req("l", TOKENS, lora=_lora("sql-adapter", 1))
    extra_l, _ = generate_block_hash_extra_keys(lora_req, 0, BLOCK, 0)
    assert extra_l == ref_extra_keys(None, "sql-adapter", 0), (
        f"live LoRA extra_keys {extra_l} missing lora name"
    )
    both = _make_req("b", TOKENS, salt="alpha", lora=_lora("sql-adapter", 1))
    extra_b, _ = generate_block_hash_extra_keys(both, 0, BLOCK, 0)
    assert extra_b == ref_extra_keys("alpha", "sql-adapter", 0), (
        f"live combined extra_keys {extra_b} != (lora, salt)"
    )
    live_hex = hash_block_tokens(
        sha256, None, TOKENS[:BLOCK], extra_b
    ).hex()
    assert live_hex == first_block_hash_hex(TOKENS, "alpha", "sql-adapter"), (
        "live hash_block_tokens diverged from independent reference"
    )
    print("state check: pass")


def test_allocate_slots_preserves_computed_prefix(report):
    init_none_hash(sha256)
    pressure = report["allocation_pressure"]
    assert pressure["allocate_slots_result"] is None, (
        "JSON allocate_slots_result must be null under tail pressure"
    )
    ids_b = pressure["computed_prefix_block_ids_before"]
    ids_a = pressure["computed_prefix_block_ids_after"]
    refs_b = pressure["computed_prefix_refcnts_before"]
    refs_a = pressure["computed_prefix_refcnts_after"]
    assert ids_b == ids_a, f"JSON prefix block ids changed {ids_b} -> {ids_a}"
    assert refs_b == refs_a, f"JSON prefix refcnts changed {refs_b} -> {refs_a}"
    assert ids_b and refs_b and len(ids_b) == len(refs_b)

    cfg = KVCacheConfig(
        num_blocks=3,
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
    warm = _make_req("warm", TOKENS)
    computed, n_hit, _ = mgr.get_computed_blocks(warm)
    allocated = mgr.allocate_slots(
        warm,
        num_new_tokens=len(TOKENS) - n_hit,
        num_new_computed_tokens=n_hit,
        new_computed_blocks=computed,
        has_scheduled_reqs=False,
    )
    assert allocated is not None, "warm prefix must allocate"

    tail = TOKENS + [1, 2, 3, 4]
    probe = _make_req("probe", tail)
    computed, n_hit, _ = mgr.get_computed_blocks(probe)
    prefix_blocks = list(computed.blocks[0]) if computed.blocks else []
    assert prefix_blocks, "follow-up must hit the cached prefix"
    before_ids = [blk.block_id for blk in prefix_blocks]
    before_refs = [blk.ref_cnt for blk in prefix_blocks]
    result = mgr.allocate_slots(
        probe,
        num_new_tokens=len(tail) - n_hit,
        num_new_computed_tokens=n_hit,
        new_computed_blocks=computed,
        has_scheduled_reqs=False,
    )
    after_ids = [blk.block_id for blk in prefix_blocks]
    after_refs = [blk.ref_cnt for blk in prefix_blocks]
    assert result is None, f"live allocate_slots under pressure returned {result}"
    assert after_ids == before_ids, (
        f"computed prefix block ids mutated {before_ids} -> {after_ids}"
    )
    assert after_refs == before_refs, (
        f"computed prefix refcnts mutated {before_refs} -> {after_refs}"
    )
    print("error handling: pass")
