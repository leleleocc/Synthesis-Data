"""Pytest wrapper around live reset_prefix_cache probes."""
from __future__ import annotations

import pytest

from probe_reset import load_report, run_live_sequence


@pytest.fixture(scope="module")
def live():
    return run_live_sequence()


@pytest.fixture(scope="module")
def report():
    return load_report()


def test_while_holders_refuse_and_preserve(live, report):
    wh = report["while_holders"]
    assert wh.get("reset_returned") is False
    assert wh.get("hash_map_still_populated") is True
    assert wh.get("inflight_block_ids") == live["while_holders"]["inflight_block_ids"]
    assert wh.get("inflight_refcnts") == live["while_holders"]["inflight_refcnts"]
    assert live["while_holders"]["reset_returned"] is False
    assert live["while_holders"]["hash_map_still_populated"] is True
    assert live["while_holders"]["ids_unchanged"] is True
    assert live["while_holders"]["refs_unchanged"] is True
    print("normal case: pass")


def test_after_free_nulls_hashes(live, report):
    af = report["after_free"]
    assert af.get("reset_returned") is True
    assert af.get("hash_map_empty") is True
    assert af.get("all_block_hashes_null") is True
    assert live["after_free"]["reset_returned"] is True
    assert live["after_free"]["hash_map_empty"] is True
    assert live["after_free"]["all_block_hashes_null"] is True
    print("edge case: pass")


def test_post_reset_shared_prefix_misses(live, report):
    pr = report["post_reset_shared_prefix"]
    assert pr.get("get_computed_blocks_hit_tokens") == 0
    assert pr.get("allocate_reused_stale_pages") is False
    assert live["post_reset_shared_prefix"]["get_computed_blocks_hit_tokens"] == 0
    print("error handling: pass")
    print("state check: pass")
