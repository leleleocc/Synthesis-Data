"""Pytest discriminator for hybrid prefix-cache configuration."""
from __future__ import annotations

import pytest

from probe_hybrid import (
    _layout_from_name,
    construct_legal,
    load_report,
    try_layout,
    try_unit,
)


@pytest.fixture(scope="module")
def report():
    return load_report()


def test_illegal_prefix_match_unit_rejected(report):
    iu = report["illegal_unit"]
    assert iu.get("prefix_match_unit") == 24
    assert iu.get("group_block_sizes") == [16, 32]
    assert iu.get("raised") is True
    assert "prefix_match_unit" in str(iu.get("error_contains", ""))
    with pytest.raises(Exception) as excinfo:
        try_unit(24)
    assert "prefix_match_unit" in str(excinfo.value)
    print("error handling: pass")


def test_illegal_mixed_hnc_layout_rejected(report):
    il = report["illegal_layout"]
    assert il.get("requested_layout") == "LHBNC"
    assert il.get("mixed_hnc") is True
    assert il.get("raised") is True
    assert "block-compact" in str(il.get("error_contains", ""))
    with pytest.raises(Exception) as excinfo:
        try_layout("LHBNC")
    assert "block-compact" in str(excinfo.value)
    print("edge case: pass")


def test_nhd_hnd_aliases(report):
    aliases = report["aliases"]
    assert aliases.get("NHD") == "LBNHC"
    assert aliases.get("HND") == "LBHNC"
    nhd = _layout_from_name("NHD")
    hnd = _layout_from_name("HND")
    assert getattr(nhd, "name", str(nhd)) == "LBNHC"
    assert getattr(hnd, "name", str(hnd)) == "LBHNC"


def test_legal_coordinator_constructs(report):
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
        assert legal.get(key) == value, f"legal.{key}={legal.get(key)!r} expected {value!r}"
    sched, hashed, name = construct_legal()
    assert sched == 32 and hashed == 16
    assert "Hybrid" in name
    print("normal case: pass")
    print("state check: pass")
