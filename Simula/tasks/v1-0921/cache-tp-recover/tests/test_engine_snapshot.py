#!/usr/bin/env python3
"""Pytest discriminator for KV failover + TP rank demotion."""

from __future__ import annotations

import json
from pathlib import Path

SNAPSHOT = Path("/workspace/engine_state_snapshot.json")
PLANTED = Path("/workspace/engine/state.json")
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "failed_rank.json"

REQUIRED = (
    "kv_cache_failover_ok",
    "tp_rank_demotion_ok",
    "ranks",
    "kv_pages_by_rank",
    "world_size",
    "tensor_parallel_size",
)


def _load(path: Path) -> object:
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise AssertionError(f"empty {path}")
    return json.loads(raw)


def test_engine_state_snapshot() -> None:
    expected = _load(FIXTURE)
    assert isinstance(expected, dict), "failed_rank.json is not an object"
    failed_rank = int(expected["failed_rank"])
    surviving = [int(x) for x in expected["surviving_ranks"]]
    pre_world = int(expected["pre_failure_world_size"])

    assert SNAPSHOT.is_file(), "missing /workspace/engine_state_snapshot.json"
    snap = _load(SNAPSHOT)
    assert isinstance(snap, dict), "snapshot is not a JSON object"

    missing = [key for key in REQUIRED if key not in snap]
    print(f"schema required: {'fail' if missing else 'pass'}" + (f" reason: missing {missing}" if missing else ""))
    assert not missing, f"missing {missing}"

    failover_ok = snap.get("kv_cache_failover_ok") is True
    demotion_ok = snap.get("tp_rank_demotion_ok") is True
    print(f"kv_cache_failover_ok: {'pass' if failover_ok else 'fail'}" + ("" if failover_ok else " reason: must be true"))
    print(f"tp_rank_demotion_ok: {'pass' if demotion_ok else 'fail'}" + ("" if demotion_ok else " reason: must be true"))
    print(
        f"coupled flags: {'pass' if failover_ok and demotion_ok else 'fail'}"
        + ("" if failover_ok and demotion_ok else " reason: both complexity_delta flags must be true")
    )
    assert failover_ok and demotion_ok

    ranks = snap.get("ranks")
    assert isinstance(ranks, list) and ranks, "ranks must be a non-empty integer array"
    assert all(isinstance(item, int) and not isinstance(item, bool) for item in ranks), "ranks must be integers"
    print(f"surviving ranks: {'pass' if ranks == surviving else 'fail'} reason: expected {surviving} got {ranks}")
    assert ranks == surviving, f"ranks must be the surviving set {surviving}, got {ranks}"
    assert failed_rank not in ranks, f"failed rank {failed_rank} still present in ranks"

    world_size = snap.get("world_size")
    tp_size = snap.get("tensor_parallel_size")
    print(f"world_size: {'pass' if world_size == len(ranks) else 'fail'} reason: world_size={world_size} ranks={ranks}")
    print(
        f"tensor_parallel_size: {'pass' if tp_size == len(ranks) else 'fail'} reason: tensor_parallel_size={tp_size}"
    )
    assert world_size == len(ranks) == tp_size, "demoted world_size and tensor_parallel_size must equal len(ranks)"
    assert world_size != pre_world, f"world_size still describes the pre-failure grid {pre_world}"

    pages = snap.get("kv_pages_by_rank")
    assert isinstance(pages, dict), "kv_pages_by_rank must be an object"
    page_keys = set(pages)
    rank_keys = {str(item) for item in ranks}
    print(f"page map keys: {'pass' if page_keys == rank_keys else 'fail'} reason: {sorted(page_keys)} vs {sorted(rank_keys)}")
    assert page_keys == rank_keys, "kv_pages_by_rank keys must be the surviving rank ids as strings"
    assert str(failed_rank) not in pages, f"pages still owned by failed rank {failed_rank}"

    live_pages: list[int] = []
    for key, values in pages.items():
        assert isinstance(values, list) and all(isinstance(item, int) and not isinstance(item, bool) for item in values), (
            f"pages for rank {key} must be integer arrays"
        )
        live_pages.extend(values)
    assert live_pages, "no live KV pages recorded"
    assert len(live_pages) == len(set(live_pages)), "duplicate page ids across ranks"
    print("page map coverage: pass")

    if PLANTED.is_file():
        planted = _load(PLANTED)
        if isinstance(planted, dict):
            planted_pages = planted.get("kv_pages_by_rank")
            rec_copy = planted_pages == pages
            print(
                f"not copied planted state: {'fail' if rec_copy else 'pass'}"
                + (" reason: snapshot copies the degraded engine/state.json page map" if rec_copy else "")
            )
            assert not rec_copy, "snapshot copies the degraded planted page map"


if __name__ == "__main__":
    try:
        test_engine_state_snapshot()
    except AssertionError as exc:
        print(f"error handling: fail reason: {exc}")
        raise SystemExit(1)
    print("error handling: pass")
    raise SystemExit(0)
