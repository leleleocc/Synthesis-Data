#!/usr/bin/env python3
"""Discriminate a restored prefix-cache + tokenizer replica report."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

REPORT = Path("/workspace/openai_compat_report.json")
HASH_FILE = Path("/workspace/repo/vllm/v1/core/kv_cache_utils.py")
DETOK_FILE = Path("/workspace/repo/vllm/tokenizers/detokenizer_utils.py")
FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "expected_offsets.json"

REQUIRED_TOP = (
    "endpoint",
    "model",
    "prefix_cache_rewrite_ok",
    "tokenizer_replica_offset_ok",
    "shared_prefix_queries",
    "tokenizer_replica",
)
REQUIRED_QUERY = (
    "prompt",
    "shared_prefix",
    "completion_text",
    "prompt_token_ids",
    "completion_token_ids",
    "shared_window_token_ids",
    "matches_shared_prefix",
)
REQUIRED_REPLICA = (
    "token_window",
    "prefix_offset",
    "read_offset",
    "replica_tokens",
    "server_tokens",
    "windows_agree",
)


def _load_json(path: Path) -> tuple[object | None, str]:
    if not path.is_file():
        return None, f"missing {path}"
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return None, f"empty {path}"
    try:
        return json.loads(raw), ""
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON in {path}: {exc}"


def check_report() -> list[tuple[str, bool, str]]:
    expected, err = _load_json(FIXTURE)
    if not isinstance(expected, dict):
        return [("fixture", False, err or "expected_offsets.json is not an object")]

    offset = int(expected["initial_incremental_detokenization_offset"])
    extra_tail = int(expected["extra_tail"])
    results: list[tuple[str, bool, str]] = []

    def rec(name: str, ok: bool, reason: str = "") -> None:
        results.append((name, ok, reason))

    report, err = _load_json(REPORT)
    if not isinstance(report, dict):
        rec("normal case", False, err or "report is not a JSON object")
        return results
    extra_keys = set(report) - set(REQUIRED_TOP)
    rec(
        "schema extra keys",
        extra_keys == set(),
        f"unexpected top-level keys {sorted(extra_keys)}" if extra_keys else "",
    )
    missing = [key for key in REQUIRED_TOP if key not in report]
    rec("schema required", not missing, f"missing {missing}")

    rec(
        "endpoint",
        isinstance(report.get("endpoint"), str) and bool(report.get("endpoint")),
        "endpoint must be a non-empty string",
    )
    rec(
        "model",
        isinstance(report.get("model"), str) and bool(report.get("model")),
        "model must be a non-empty string",
    )

    rewrite_ok = report.get("prefix_cache_rewrite_ok") is True
    replica_ok = report.get("tokenizer_replica_offset_ok") is True
    rec("prefix cache rewrite flag", rewrite_ok, "prefix_cache_rewrite_ok must be true")
    rec("tokenizer replica offset flag", replica_ok, "tokenizer_replica_offset_ok must be true")
    rec(
        "coupled flags",
        rewrite_ok and replica_ok,
        "both complexity_delta flags must be true together",
    )

    queries = report.get("shared_prefix_queries")
    rec(
        "shared prefix query count",
        isinstance(queries, list) and len(queries) >= 2,
        "shared_prefix_queries must contain at least two entries",
    )
    if not isinstance(queries, list) or len(queries) < 2:
        return results

    prompts: list[str] = []
    prefixes: list[str] = []
    windows: list[list[int]] = []
    for index, query in enumerate(queries):
        label = f"query[{index}]"
        if not isinstance(query, dict):
            rec(label, False, "query must be an object")
            continue
        q_missing = [key for key in REQUIRED_QUERY if key not in query]
        rec(f"{label} schema", not q_missing, f"missing {q_missing}")
        q_extra = set(query) - set(REQUIRED_QUERY)
        rec(
            f"{label} extra keys",
            q_extra == set(),
            f"unexpected query keys {sorted(q_extra)}" if q_extra else "",
        )
        prompt = query.get("prompt")
        prefix = query.get("shared_prefix")
        rec(
            f"{label} prompt",
            isinstance(prompt, str) and bool(prompt),
            "prompt must be a non-empty string",
        )
        rec(
            f"{label} shared_prefix",
            isinstance(prefix, str) and bool(prefix),
            "shared_prefix must be a non-empty string",
        )
        rec(
            f"{label} prompt uses prefix",
            isinstance(prompt, str)
            and isinstance(prefix, str)
            and prompt.startswith(prefix)
            and prompt != prefix,
            "prompt must start with shared_prefix and then continue past it",
        )
        rec(
            f"{label} matches_shared_prefix",
            query.get("matches_shared_prefix") is True,
            "matches_shared_prefix must be true",
        )
        prompt_ids = query.get("prompt_token_ids")
        window_ids = query.get("shared_window_token_ids")
        completion_ids = query.get("completion_token_ids")
        rec(
            f"{label} prompt_token_ids",
            isinstance(prompt_ids, list)
            and prompt_ids
            and all(isinstance(item, int) and not isinstance(item, bool) for item in prompt_ids),
            "prompt_token_ids must be a non-empty integer array",
        )
        rec(
            f"{label} shared_window_token_ids",
            isinstance(window_ids, list)
            and window_ids
            and all(isinstance(item, int) and not isinstance(item, bool) for item in window_ids),
            "shared_window_token_ids must be a non-empty integer array",
        )
        rec(
            f"{label} completion_token_ids",
            isinstance(completion_ids, list)
            and all(isinstance(item, int) and not isinstance(item, bool) for item in completion_ids),
            "completion_token_ids must be an integer array",
        )
        rec(
            f"{label} window is prompt prefix",
            isinstance(prompt_ids, list)
            and isinstance(window_ids, list)
            and len(window_ids) <= len(prompt_ids)
            and prompt_ids[: len(window_ids)] == window_ids,
            "shared_window_token_ids must be the overlapping prefix of prompt_token_ids",
        )
        rec(
            f"{label} not copied prompt ids",
            window_ids != prompt_ids,
            "shared window must be the overlap, not a copy of the full prompt ids",
        )
        if isinstance(prompt, str):
            prompts.append(prompt)
        if isinstance(prefix, str):
            prefixes.append(prefix)
        if isinstance(window_ids, list):
            windows.append(window_ids)

    rec("distinct prompts", len(set(prompts)) == len(prompts), "the two prompts must be distinct")
    rec(
        "common shared_prefix",
        len(set(prefixes)) == 1 and bool(prefixes[0]),
        "queries must share one shared_prefix",
    )
    rec(
        "identical shared windows",
        bool(windows) and all(item == windows[0] for item in windows),
        "shared_window_token_ids must be the same overlapping token-id window",
    )

    replica = report.get("tokenizer_replica")
    if not isinstance(replica, dict):
        rec("tokenizer_replica", False, "tokenizer_replica must be an object")
        return results
    r_missing = [key for key in REQUIRED_REPLICA if key not in replica]
    rec("replica schema", not r_missing, f"missing {r_missing}")
    r_extra = set(replica) - set(REQUIRED_REPLICA)
    rec(
        "replica extra keys",
        r_extra == set(),
        f"unexpected replica keys {sorted(r_extra)}" if r_extra else "",
    )
    token_window = replica.get("token_window")
    rec(
        "replica token_window",
        isinstance(token_window, list)
        and token_window
        and all(isinstance(item, int) and not isinstance(item, bool) for item in token_window),
        "token_window must be a non-empty integer array",
    )
    rec(
        "replica window matches queries",
        bool(windows) and token_window == windows[0],
        "tokenizer_replica.token_window must be the same shared window",
    )
    rec("windows_agree", replica.get("windows_agree") is True, "windows_agree must be true")

    prefix_offset = replica.get("prefix_offset")
    read_offset = replica.get("read_offset")
    replica_tokens = replica.get("replica_tokens")
    server_tokens = replica.get("server_tokens")
    rec(
        "prefix_offset",
        isinstance(prefix_offset, int) and not isinstance(prefix_offset, bool) and prefix_offset >= 0,
        "prefix_offset must be a non-negative integer",
    )
    rec(
        "read_offset",
        isinstance(read_offset, int) and not isinstance(read_offset, bool) and read_offset >= 0,
        "read_offset must be a non-negative integer",
    )
    rec(
        "replica_tokens",
        isinstance(replica_tokens, list)
        and replica_tokens
        and all(isinstance(item, str) for item in replica_tokens),
        "replica_tokens must be a non-empty string array",
    )
    rec(
        "server_tokens",
        isinstance(server_tokens, list)
        and server_tokens
        and all(isinstance(item, str) for item in server_tokens),
        "server_tokens must be a non-empty string array",
    )
    rec(
        "replica/server alignment",
        replica_tokens == server_tokens,
        "replica_tokens and server_tokens must agree on the hashed window",
    )

    if isinstance(replica_tokens, list) and replica_tokens:
        expected_read = len(replica_tokens)
        expected_prefix = max(expected_read - offset, 0)
        rec(
            "replica offset pairing",
            read_offset == expected_read and prefix_offset == expected_prefix,
            f"expected prefix_offset={expected_prefix} read_offset={expected_read} "
            f"(offset {offset} with extra tail {extra_tail}), got "
            f"prefix_offset={prefix_offset} read_offset={read_offset}",
        )
        rec(
            "negative space swapped offsets",
            not (prefix_offset == expected_read and read_offset == max(expected_read - offset, 0)),
            "prefix/read pairing is still swapped against the hashed window",
        )

    vllm_bin = Path("/opt/venv/bin/vllm")
    rec(
        "vllm entrypoint",
        vllm_bin.is_file() or shutil.which("vllm") is not None,
        "drive checks through /opt/venv/bin/vllm; binary is missing",
    )

    if not HASH_FILE.is_file():
        rec("hash source", False, f"missing {HASH_FILE}")
    else:
        hash_text = HASH_FILE.read_text(encoding="utf-8")
        rec(
            "hash full token window",
            "tuple(curr_block_token_ids)" in hash_text
            and "tuple(curr_block_token_ids[5:])" not in hash_text,
            "prefix fingerprint still hashes curr_block_token_ids[5:] instead of the true window",
        )
        rec(
            "hash extra_keys",
            "curr_block_token_ids_tuple, extra_keys" in hash_text,
            "prefix fingerprint still drops extra_keys",
        )

    if not DETOK_FILE.is_file():
        rec("detok source", False, f"missing {DETOK_FILE}")
    else:
        detok_text = DETOK_FILE.read_text(encoding="utf-8")
        rec(
            "detok offset constant",
            "INITIAL_INCREMENTAL_DETOKENIZATION_OFFSET = 5" in detok_text,
            "tokenizer replica offset constant is not 5",
        )
        rec(
            "detok extra tail",
            "INITIAL_INCREMENTAL_DETOKENIZATION_OFFSET - 2" in detok_text,
            "tokenizer replica dropped the extra +2 special-token tail",
        )
        rec(
            "detok prefix/read pairing",
            "prefix_offset = max(read_offset - INITIAL_INCREMENTAL_DETOKENIZATION_OFFSET, 0)"
            in detok_text,
            "prefix/read offsets are not the restored replica pairing",
        )
        rec(
            "negative space detok skip-5",
            "prompt_ids[-INITIAL_INCREMENTAL_DETOKENIZATION_OFFSET :]" not in detok_text
            or "INITIAL_INCREMENTAL_DETOKENIZATION_OFFSET - 2" in detok_text,
            "detokenizer still converts only the skip-5 window",
        )

    return results
