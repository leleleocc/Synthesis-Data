"""Discriminator for ChatCompletionRequest guards and SamplingParams mapping."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/workspace/repo")

from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest

REPORT = Path("/workspace/sampling_params.json")
DEFAULTS = {"stop_token_ids": [99, 2]}
ILLEGAL = [
    (
        Path("/workspace/requests/stream_prompt_logprobs.json"),
        "prompt_logprobs",
    ),
    (
        Path("/workspace/requests/top_logprobs_without_logprobs.json"),
        "logprobs",
    ),
    (
        Path("/workspace/requests/logprob_token_ids_without_logprobs.json"),
        "logprobs",
    ),
]
LEGAL = Path("/workspace/requests/echo_stops.json")


def _load() -> dict:
    assert REPORT.is_file(), f"missing {REPORT}"
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    extra = set(data) - {"illegal", "mapped"}
    assert not extra, f"unexpected top-level keys {sorted(extra)}"
    return data


@pytest.fixture(scope="module")
def report():
    return _load()


def _validate(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ChatCompletionRequest.model_validate(payload)


def test_illegal_bodies_rejected_live_and_reported(report):
    rows = report["illegal"]
    assert isinstance(rows, list) and len(rows) == 3
    for row, (path, needle) in zip(rows, ILLEGAL, strict=True):
        assert row["path"] == str(path)
        assert row["accepted"] is False, f"{path} reported accepted"
        err = str(row.get("error_contains") or "")
        assert needle in err.lower() or needle in err, (
            f"{path} error_contains {err!r} missing {needle}"
        )
        with pytest.raises(Exception) as excinfo:
            _validate(path)
        msg = str(excinfo.value)
        assert needle in msg, f"live validate({path}) error {msg!r} missing {needle}"
        if path.name == "stream_prompt_logprobs.json":
            assert "prompt_logprobs" in msg.lower() or "prompt_logprobs" in msg
    print("error handling: pass")


def test_legal_echo_stop_and_logprob_token_ids_mapping(report):
    mapped = report["mapped"]
    assert isinstance(mapped, list) and len(mapped) == 1
    row = mapped[0]
    assert row["path"] == str(LEGAL)
    assert row["prompt_logprobs"] == 5
    assert row["logprobs"] is None
    assert row["logprob_token_ids"] == [11, 13]
    assert row["stop_token_ids"] == [1, 2, 99]

    req = _validate(LEGAL)
    sp = req.to_sampling_params(max_tokens=16, default_sampling_params=DEFAULTS)
    assert sp.prompt_logprobs == 5, f"echo did not fill prompt_logprobs, got {sp.prompt_logprobs}"
    assert sp.logprobs is None, (
        f"logprob_token_ids set but SamplingParams.logprobs={sp.logprobs}"
    )
    assert list(sp.logprob_token_ids or []) == [11, 13]
    assert list(sp.stop_token_ids or []) == [1, 2, 99], (
        f"stop merge produced {sp.stop_token_ids}, expected [1, 2, 99]"
    )
    print("normal case: pass")


def test_negative_space_stream_and_flag_guards():
    # Mapping without guards would accept these.
    with pytest.raises(Exception) as stream_exc:
        _validate(ILLEGAL[0][0])
    assert "stream" in str(stream_exc.value).lower() or "prompt_logprobs" in str(stream_exc.value)

    with pytest.raises(Exception) as top_exc:
        _validate(ILLEGAL[1][0])
    assert "logprobs" in str(top_exc.value)

    with pytest.raises(Exception) as ids_exc:
        _validate(ILLEGAL[2][0])
    assert "logprobs" in str(ids_exc.value)

    print("edge case: pass")
    print("state check: pass")
